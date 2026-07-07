from pathlib import Path

from fixsub.alignment import score_alignment
from fixsub.subtitles import parse_subtitle_intervals


def test_parse_srt_intervals(tmp_path: Path) -> None:
    subtitle = tmp_path / "movie.srt"
    subtitle.write_text(
        "1\n00:00:05,000 --> 00:00:07,000\nHello\n\n2\n00:01:00,500 --> 00:01:02,000\nWorld\n",
        encoding="utf-8",
    )

    intervals = parse_subtitle_intervals(subtitle)

    assert intervals == [(5.0, 7.0), (60.5, 62.0)]


def test_parse_ass_intervals(tmp_path: Path) -> None:
    subtitle = tmp_path / "movie.ass"
    subtitle.write_text(
        "[Events]\nDialogue: 0,0:00:05.00,0:00:07.00,Default,,0,0,0,,Hello\n",
        encoding="utf-8",
    )

    intervals = parse_subtitle_intervals(subtitle)

    assert intervals == [(5.0, 7.0)]


def test_alignment_scores_plausible_subtitle_high(tmp_path: Path) -> None:
    subtitle = tmp_path / "movie.srt"
    subtitle.write_text(
        "1\n00:02:00,000 --> 00:02:02,000\nA\n\n2\n00:30:00,000 --> 00:30:03,000\nB\n\n3\n01:40:00,000 --> 01:40:04,000\nC\n",
        encoding="utf-8",
    )

    score = score_alignment(subtitle, duration_seconds=7200)

    assert score.score >= 0.7


def test_alignment_scores_out_of_video_subtitle_low(tmp_path: Path) -> None:
    subtitle = tmp_path / "bad.srt"
    subtitle.write_text(
        "1\n03:00:00,000 --> 03:00:02,000\nToo late\n",
        encoding="utf-8",
    )

    score = score_alignment(subtitle, duration_seconds=7200)

    assert score.score < 0.5
    assert any("outside video" in reason for reason in score.reasons)
