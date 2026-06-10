"""Клиент OBS WebSocket v5 (OBS 28+)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import uuid
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

logger = logging.getLogger(__name__)

_OP_HELLO = 0
_OP_IDENTIFY = 1
_OP_IDENTIFIED = 2
_OP_EVENT = 5
_OP_REQUEST = 6
_OP_REQUEST_RESPONSE = 7


def _obs_auth(password: str, salt: str, challenge: str) -> str:
    secret = base64.b64encode(
        hashlib.sha256((password + salt).encode("utf-8")).digest()
    ).decode("utf-8")
    auth = hashlib.sha256((secret + challenge).encode("utf-8")).digest()
    return base64.b64encode(auth).decode("utf-8")


class ObsWebSocketClient:
    def __init__(
        self,
        host: str,
        port: int,
        *,
        password: str = "",
        rpc_version: int = 1,
    ) -> None:
        self._url = f"ws://{host}:{port}"
        self._password = password
        self._rpc_version = rpc_version

    async def trigger_hotkey(self, hotkey_name: str, *, context_name: str = "OBS") -> None:
        await self._execute(
            "TriggerHotkeyByName",
            {"hotkeyName": hotkey_name, "contextName": context_name},
        )

    async def set_program_scene(self, scene_name: str) -> None:
        await self._execute(
            "SetCurrentProgramScene",
            {"sceneName": scene_name},
        )

    async def get_current_program_scene(self) -> str:
        data = await self._execute("GetCurrentProgramScene")
        return str(data.get("currentProgramSceneName", ""))

    async def get_stream_active(self) -> bool:
        data = await self._execute("GetStreamStatus")
        return bool(data.get("outputActive"))

    async def start_stream(self) -> None:
        await self._execute("StartStream")

    async def stop_stream(self) -> None:
        await self._execute("StopStream")

    async def _execute(self, request_type: str, request_data: dict[str, Any] | None = None) -> dict[str, Any]:
        async with websockets.connect(self._url, open_timeout=5) as ws:
            await self._identify(ws)
            return await self._request(ws, request_type, request_data)

    async def _identify(self, ws: ClientConnection) -> None:
        hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if hello.get("op") != _OP_HELLO:
            raise RuntimeError(f"OBS: ожидался Hello, получено op={hello.get('op')}")

        identify: dict[str, Any] = {"rpcVersion": self._rpc_version}
        auth_info = hello.get("d", {}).get("authentication")
        if auth_info:
            if not self._password:
                raise RuntimeError("OBS требует пароль WebSocket (OBS_WEBSOCKET_PASSWORD)")
            identify["authentication"] = _obs_auth(
                self._password,
                auth_info["salt"],
                auth_info["challenge"],
            )

        await ws.send(json.dumps({"op": _OP_IDENTIFY, "d": identify}))

        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            op = msg.get("op")
            if op == _OP_IDENTIFIED:
                if msg.get("d", {}).get("negotiatedRpcVersion") is None:
                    raise RuntimeError("OBS: идентификация не удалась")
                return
            if op == _OP_EVENT:
                continue
            raise RuntimeError(f"OBS: неожиданный ответ при Identify op={op}")

    async def _request(
        self,
        ws: ClientConnection,
        request_type: str,
        request_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        request_id = str(uuid.uuid4())
        await ws.send(
            json.dumps(
                {
                    "op": _OP_REQUEST,
                    "d": {
                        "requestType": request_type,
                        "requestId": request_id,
                        "requestData": request_data or {},
                    },
                }
            )
        )

        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            if msg.get("op") == _OP_EVENT:
                continue
            if msg.get("op") != _OP_REQUEST_RESPONSE:
                continue
            data = msg.get("d", {})
            if data.get("requestId") != request_id:
                continue
            status = data.get("requestStatus", {})
            if status.get("result") is not True:
                comment = status.get("comment", "unknown error")
                raise RuntimeError(f"OBS {request_type}: {comment}")
            return data.get("responseData") or {}
