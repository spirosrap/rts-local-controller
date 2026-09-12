import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from rts_controller.ra2 import Reader, BridgeError, PREFIX, unpack


def envelope(name, **fields):
    return {"body": {"@type": PREFIX+"ra2yrproto.PollResults", "result": {"results": [
        {"result": {"@type": PREFIX+"ra2yrproto.commands."+name, **fields}}]}}}


def game(frame=1):
    return {"stage": "STAGE_INGAME", "currentFrame": frame,
            "houses": [{"currentPlayer": True, "self": 42}],
            "objects": [{"pointerSelf": 100, "pointerHouse": 42, "health": 125,
                         "selected": True, "onMap": True, "coordinates": {"x": 256, "y": 512}},
                        {"pointerSelf": 200, "pointerHouse": 99, "health": 999}]}


class ReaderTests(unittest.TestCase):
    def test_envelope_and_error_validation(self):
        self.assertIn("state", unpack(envelope("GetGameState", state=game()), "GetGameState"))
        for response in ({}, {"code": "ERROR"}, envelope("Wrong")):
            with self.assertRaises(BridgeError): unpack(response, "GetGameState")

    def test_single_step_never_requests_game_state(self):
        reader = Reader()
        with patch.object(reader, "_read", return_value={"config": {"singleStep": True}}) as read:
            with self.assertRaises(BridgeError): reader.observe()
            read.assert_called_once_with("InspectConfiguration")

    def test_own_units_only_and_unchanged_frame_age(self):
        reader = Reader()
        with patch.object(reader, "_read", side_effect=lambda n:
                          {"config": {}} if n == "InspectConfiguration" else {"state": game()}):
            with patch("rts_controller.ra2.time.monotonic", side_effect=[1, 1.1, 2, 2.1]):
                first, second = reader.observe(), reader.observe()
        self.assertEqual([u["id"] for u in first["own_objects"]], ["100"])
        self.assertEqual(second["frame_unchanged_ms"], 1000)
        self.assertFalse(first["control_ready"])

    def test_frame_reset_fails_closed(self):
        reader = Reader(); reader.frame = 10
        with patch.object(reader, "_read", side_effect=[{"config": {}}, {"state": game(1)}]):
            with self.assertRaises(BridgeError): reader.observe()

    def test_real_http_transport_with_synthetic_server(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                command = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(command)
                name = command["command"]["@type"].rsplit(".", 1)[1]
                payload = envelope(name, config={}) if name == "InspectConfiguration" else envelope(name, state=game())
                body = json.dumps(payload).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            result = Reader(server.server_port).observe()
            self.assertEqual(result["own_objects"][0]["health"], 125)
            self.assertEqual(len(requests), 2)
            self.assertNotIn("update", requests[0]["command"])
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__": unittest.main()
