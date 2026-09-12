"""Persistent, correlated game-order transport. Never resubmits an order."""
import json
import time
from .ra2 import BridgeError, PREFIX, LIMIT, unpack


class Orders:
    def __init__(self, port=14521, timeout=.4):
        if not 1 <= port <= 65535 or not 0 < timeout <= 1:
            raise ValueError("Invalid port or timeout")
        self.port, self.timeout, self.socket = port, timeout, None

    def request(self, name, fields, *, on_queued=None, on_uncertain=None):
        if name not in {"UnitCommand", "MissionClicked"}:
            raise BridgeError("Unsupported game order")
        try:
            import websocket
        except ImportError as error:
            raise BridgeError("Install the ra2 extra for live orders: pip install '.[ra2]'") from error
        submitted = False
        completed = False
        try:
            if self.socket is None:
                self.socket = websocket.create_connection(
                    f"ws://127.0.0.1:{self.port}/", timeout=self.timeout,
                    http_no_proxy=["127.0.0.1"])
            deadline = time.monotonic() + self.timeout

            def exchange(command):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise BridgeError("Order result timed out; outcome uncertain, not retried")
                self.socket.settimeout(remaining)
                self.socket.send_binary(json.dumps(command).encode("utf-8"))
                raw = self.socket.recv()
                if len(raw) > LIMIT:
                    raise BridgeError("Order response exceeds size limit")
                response = json.loads(raw)
                if response.get("code", "OK") not in ("OK", 0):
                    raise BridgeError("Order transport error")
                return response

            submitted = True
            ack = exchange({"commandType": "CLIENT_COMMAND", "blocking": False,
                            "command": {"@type": PREFIX + "ra2yrproto.commands." + name, **fields}})
            body = ack["body"]
            if body["@type"] != PREFIX + "ra2yrproto.RunCommandAck" or not body.get("id"):
                raise BridgeError("Missing order acknowledgment")
            command_id = str(body["id"])
            if on_queued is not None:
                on_queued()
                deadline = time.monotonic() + self.timeout
            while True:
                response = exchange({"commandType": "POLL"})
                body = response["body"]
                if body["@type"] != PREFIX + "ra2yrproto.PollResults":
                    raise BridgeError("Unexpected order poll envelope")
                results = body.get("result", {}).get("results", [])
                if results:
                    if len(results) != 1 or str(results[0].get("commandId")) != command_id:
                        raise BridgeError("Order result correlation failed")
                    payload = unpack(response, name)
                    completed = True
                    return payload
                if time.monotonic() >= deadline:
                    raise BridgeError("Order result timed out; outcome uncertain, not retried")
                time.sleep(min(.005, max(0, deadline-time.monotonic())))
        except (OSError, websocket.WebSocketException, ValueError, KeyError, TypeError, AttributeError) as error:
            raise BridgeError(f"Order transport failed; outcome uncertain, not retried: {error}") from error
        finally:
            # A pending callback may still belong to the engine. The paused
            # lab controller terminates its verified test process before
            # disconnecting on uncertainty, rather than retrying a command.
            if submitted and not completed and on_uncertain is not None:
                on_uncertain()
            # A fresh connection per order keeps result queues isolated, but
            # remains open for acknowledgment and every completion poll.
            self.close()

    def close(self):
        if self.socket is not None:
            self.socket.close(timeout=0)
            self.socket = None
