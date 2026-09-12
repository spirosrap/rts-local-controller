import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from rts_controller.ra2 import BridgeError, PREFIX
from rts_controller.ra2_orders import Orders


class OrdersTests(unittest.TestCase):
    def transport(self, replies):
        socket = Mock()
        socket.recv.side_effect = [json.dumps(r) for r in replies]
        module = SimpleNamespace(create_connection=Mock(return_value=socket),
                                 WebSocketException=OSError)
        return socket, module

    def ack(self):
        return {"body": {"@type": PREFIX+"ra2yrproto.RunCommandAck", "id": "10"}}

    def result(self, command_id="10", code="OK"):
        return {"body": {"@type": PREFIX+"ra2yrproto.PollResults", "result": {"results": [
            {"commandId": command_id, "resultCode": code, "result": {
                "@type": PREFIX+"ra2yrproto.commands.UnitCommand"}}]}}}

    def test_empty_poll_is_not_a_resubmission(self):
        empty = {"body": {"@type": PREFIX+"ra2yrproto.PollResults", "result": {}}}
        socket, module = self.transport([self.ack(), empty, self.result()])
        with patch.dict("sys.modules", websocket=module):
            Orders().request("UnitCommand", {"objectAddresses": [100], "action": "UNIT_ACTION_SELECT"})
        sent = [json.loads(c.args[0]) for c in socket.send_binary.call_args_list]
        self.assertEqual([s["commandType"] for s in sent], ["CLIENT_COMMAND", "POLL", "POLL"])
        socket.close.assert_called_once_with(timeout=0)

    def test_wrong_id_and_error_result_fail(self):
        for result in (self.result("11"), self.result(code="ERROR")):
            socket, module = self.transport([self.ack(), result])
            with patch.dict("sys.modules", websocket=module):
                with self.assertRaises(BridgeError): Orders().request("UnitCommand", {})
            socket.close.assert_called_once()

    def test_timeout_never_resends_order(self):
        socket, module = self.transport([])
        socket.recv.side_effect = TimeoutError("timed out")
        with patch.dict("sys.modules", websocket=module):
            with self.assertRaises(BridgeError): Orders().request("UnitCommand", {})
        self.assertEqual(socket.send_binary.call_count, 1)
        socket.close.assert_called_once()

    def test_unknown_order_denied(self):
        with self.assertRaises(BridgeError): Orders().request("Unknown", {})

    def test_queued_callback_runs_before_poll(self):
        socket, module = self.transport([self.ack(), self.result()])
        def queued(): self.assertEqual(socket.send_binary.call_count, 1)
        recover = Mock()
        with patch.dict("sys.modules", websocket=module):
            Orders().request("UnitCommand", {}, on_queued=queued, on_uncertain=recover)
        recover.assert_not_called()

    def test_uncertainty_recovers_before_disconnect(self):
        socket, module = self.transport([])
        socket.recv.side_effect = TimeoutError("timed out")
        def recover(): socket.close.assert_not_called()
        with patch.dict("sys.modules", websocket=module):
            with self.assertRaises(BridgeError): Orders().request("UnitCommand", {}, on_uncertain=recover)
        socket.close.assert_called_once()
