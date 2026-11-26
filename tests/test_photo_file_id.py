"""照片远端标识用例测试

- 覆盖首次上传记标识、同一份文件按标识重发、文件重画即失效
- 覆盖标识被平台拒掉即回退重传本体，文件取不到即不参与缓存
"""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram.exceptions import TelegramAPIError  # noqa: E402
from aiogram.methods import SendMessage  # noqa: E402

from finshin_adapter_tg import _media as media_mod  # noqa: E402
from finshin_adapter_tg._config import PLATFORM  # noqa: E402
from finshin_adapter_tg._interaction import (  # noqa: E402
    TelegramInteractionPort,
)
from finshin_sdk.domain import ContentKind  # noqa: E402
from finshin_sdk.domain.ids import ContainerCode, UserId  # noqa: E402
from finshin_sdk.dto import OutboundPayloadDTO, PrincipalDTO  # noqa: E402

_SENT_ID = "PHOTO-ID-1"  # 上传回执里的标识


def _payload(path: str) -> OutboundPayloadDTO:
    return OutboundPayloadDTO(kind=ContentKind.PHOTO, local_path=path)


def _principal() -> PrincipalDTO:
    return PrincipalDTO(
        platform=PLATFORM, container=ContainerCode("u456"), user=UserId("456")
    )


class _FakeSent:
    def __init__(self) -> None:
        self.message_id = 999
        self.photo = [SimpleNamespace(file_id=_SENT_ID)]


class _FakeBot:
    """按 photo 参数是本体还是标识记下每一趟"""

    def __init__(self) -> None:
        self.sources: list[str] = []
        self.reject_id = False

    async def send_photo(self, **kwargs: object) -> _FakeSent:
        if isinstance(kwargs["photo"], str):
            self.sources.append("标识")
            if self.reject_id:
                raise TelegramAPIError(
                    method=SendMessage(chat_id=1, text="x"), message="标识失效"
                )
        else:
            self.sources.append("本体")
        return _FakeSent()


class _PhotoCase(unittest.IsolatedAsyncioTestCase):
    """一份真实临时图撑起的公共现场"""

    async def asyncSetUp(self) -> None:
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.path = Path(holder.name) / "help.png"
        self.path.write_bytes(b"png-bytes")
        self.bot = _FakeBot()
        self.lines: list[str] = []
        note = patch.object(media_mod, "note", side_effect=self.lines.append)
        note.start()
        self.addCleanup(note.stop)
        self.port = TelegramInteractionPort(self.bot)  # type: ignore[arg-type]


class TestPhotoIdReuse(_PhotoCase):
    """同文件重发"""

    async def test_first_send_uploads_body(self) -> None:
        await self.port.send_message(_principal(), _payload(str(self.path)))
        self.assertEqual(self.bot.sources, ["本体"])
        self.assertEqual(self.lines, [f"照片上传本体：{_SENT_ID}"])

    async def test_second_send_reuses_id(self) -> None:
        payload = _payload(str(self.path))
        await self.port.send_message(_principal(), payload)
        await self.port.send_message(_principal(), payload)
        self.assertEqual(self.bot.sources, ["本体", "标识"])
        self.assertEqual(self.lines[-1], f"照片按标识重发：{_SENT_ID}")

    async def test_rewritten_file_uploads_again(self) -> None:
        await self.port.send_message(_principal(), _payload(str(self.path)))
        self.path.write_bytes(b"redrawn-png-bytes")
        await self.port.send_message(_principal(), _payload(str(self.path)))
        self.assertEqual(self.bot.sources, ["本体", "本体"])

    async def test_missing_file_stays_out_of_the_cache(self) -> None:
        await self.port.send_message(_principal(), _payload("不在的图.png"))
        self.assertEqual(self.bot.sources, ["本体"])
        self.assertEqual(self.lines, [])


class TestPhotoIdRejected(_PhotoCase):
    """标识被平台拒掉"""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.bot.reject_id = True

    async def test_stale_id_falls_back_to_body(self) -> None:
        payload = _payload(str(self.path))
        await self.port.send_message(_principal(), payload)
        await self.port.send_message(_principal(), payload)
        self.assertEqual(self.bot.sources, ["本体", "标识", "本体"])
        self.assertEqual(self.lines[-1], f"照片上传本体：{_SENT_ID}")


if __name__ == "__main__":
    unittest.main()
