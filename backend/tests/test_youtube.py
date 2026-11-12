"""Los enlaces de YouTube. Sin red salvo la prueba `slow`."""

from __future__ import annotations

from pathlib import Path

import pytest
import soundfile as sf
import yt_dlp

from mewsplit import youtube


@pytest.mark.parametrize(
    "link",
    [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",
        "https://youtube.com/watch?v=jNQXAC9IVRw&t=42s",
        "https://www.youtube.com/watch?v=jNQXAC9IVRw&list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG",
        "https://m.youtube.com/watch?v=jNQXAC9IVRw",
        "https://music.youtube.com/watch?v=jNQXAC9IVRw&si=abc",
        "https://youtu.be/jNQXAC9IVRw",
        "https://youtu.be/jNQXAC9IVRw?si=Xyz123",
        "https://www.youtube.com/shorts/jNQXAC9IVRw",
        "https://www.youtube.com/live/jNQXAC9IVRw?feature=share",
        "https://www.youtube.com/embed/jNQXAC9IVRw",
        "youtu.be/jNQXAC9IVRw",
        "  www.youtube.com/watch?v=jNQXAC9IVRw\n",
    ],
)
def test_every_form_of_a_video_link_gives_its_id(link):
    assert youtube.video_id(link) == "jNQXAC9IVRw"


@pytest.mark.parametrize(
    "link",
    [
        "",
        "hola",
        "https://www.youtube.com/playlist?list=PLx0sYbCqOb8TBPRdmBHs5Iftvv9TPboYG",
        "https://www.youtube.com/@jawed",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=corto",
        "https://vimeo.com/76979871",
        "https://youtube.com.example.com/watch?v=jNQXAC9IVRw",
        "https://example.com/youtu.be/jNQXAC9IVRw",
    ],
)
def test_anything_else_is_rejected(link):
    with pytest.raises(youtube.InvalidLink):
        youtube.video_id(link)


def test_the_reason_drops_the_yt_dlp_prefix():
    message = "ERROR: [youtube] jNQXAC9IVRw: Private video. Sign in if you've been granted access"
    assert youtube._reason(message) == "Private video. Sign in if you've been granted access"


class FakeYoutubeDL:
    """Falla la descarga con los errores dados, en orden, y luego la completa."""

    def __init__(self, failures: list[str]):
        self.failures = failures
        self.downloads = 0

    def __call__(self, options):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        return {"title": "Me at the zoo"}

    def process_ie_result(self, info, download):
        self.downloads += 1
        if self.failures:
            raise yt_dlp.utils.DownloadError(self.failures.pop(0))
        return {"requested_downloads": [{"filepath": "/descargas/audio.opus"}]}


@pytest.fixture
def fake_ydl(monkeypatch):
    def install(*failures: str) -> FakeYoutubeDL:
        fake = FakeYoutubeDL(list(failures))
        monkeypatch.setattr(yt_dlp, "YoutubeDL", fake)
        monkeypatch.setattr(youtube, "ensure_ffmpeg", lambda: None)
        return fake

    return install


FORBIDDEN = "ERROR: unable to download video data: HTTP Error 403: Forbidden"


def test_a_403_is_retried_with_a_fresh_url(fake_ydl, tmp_path: Path):
    fake = fake_ydl(FORBIDDEN, FORBIDDEN)

    assert youtube.download("jNQXAC9IVRw", tmp_path) == Path("/descargas/audio.opus")
    assert fake.downloads == 3


def test_a_403_that_persists_gives_up(fake_ydl, tmp_path: Path):
    fake = fake_ydl(*[FORBIDDEN] * youtube.ATTEMPTS)

    with pytest.raises(youtube.Unavailable, match="403"):
        youtube.download("jNQXAC9IVRw", tmp_path)
    assert fake.downloads == youtube.ATTEMPTS


def test_other_failures_are_not_retried(fake_ydl, tmp_path: Path):
    fake = fake_ydl("ERROR: [youtube] jNQXAC9IVRw: Private video")

    with pytest.raises(youtube.Unavailable, match="Private video"):
        youtube.download("jNQXAC9IVRw", tmp_path)
    assert fake.downloads == 1


@pytest.mark.slow
def test_downloads_real_audio_that_soundfile_reads(tmp_path: Path):
    """Lo primero que se rompe cuando YouTube cambia algo: córrela tras actualizar yt-dlp."""
    titles: list[str] = []
    progress: list[float] = []

    audio = youtube.download(
        "jNQXAC9IVRw", tmp_path, on_title=titles.append, on_progress=progress.append
    )

    assert titles == ["Me at the zoo"]
    assert progress and progress[-1] == 1.0
    info = sf.info(str(audio))
    assert info.subtype == "OPUS"
    assert 18 < info.duration < 20
