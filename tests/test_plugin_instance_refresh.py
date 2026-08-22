from datetime import datetime, timezone

from src.model import PluginInstance


def make_plugin(refresh, latest_refresh_time=None):
    return PluginInstance(plugin_id="p1", name="inst", settings={}, refresh=refresh, latest_refresh_time=latest_refresh_time)


def test_never_refreshed_with_and_without_scheduled():
    # no scheduled -> should refresh immediately
    p = make_plugin(refresh={})
    now = datetime(2022, 1, 2, 14, 0, 0)
    assert p.should_refresh(now) is True

    # scheduled in future -> should not refresh
    p = make_plugin(refresh={"scheduled": "15:00"})
    now = datetime(2022, 1, 2, 14, 0, 0)
    assert p.should_refresh(now) is False

    # scheduled at or before current time -> should refresh
    p = make_plugin(refresh={"scheduled": "14:00"})
    now = datetime(2022, 1, 2, 14, 0, 0)
    assert p.should_refresh(now) is True


def test_interval_refresh_naive_datetimes():
    # latest refresh 2 minutes ago, interval 60s -> should refresh
    latest = datetime(2022, 1, 2, 14, 0, 0)
    p = make_plugin(refresh={"interval": 60}, latest_refresh_time=latest.isoformat())
    now = datetime(2022, 1, 2, 14, 2, 0)
    assert p.should_refresh(now) is True

    # latest refresh 30s ago, interval 120s -> should not refresh
    latest = datetime(2022, 1, 2, 14, 1, 30)
    p = make_plugin(refresh={"interval": 120}, latest_refresh_time=latest.isoformat())
    now = datetime(2022, 1, 2, 14, 2, 0)
    assert p.should_refresh(now) is False


def test_interval_refresh_timezone_aware_datetimes():
    # use timezone-aware datetimes for both latest and current times
    latest = datetime(2022, 1, 2, 14, 0, 0, tzinfo=timezone.utc)
    p = make_plugin(refresh={"interval": 60}, latest_refresh_time=latest.isoformat())
    now = datetime(2022, 1, 2, 14, 2, 0, tzinfo=timezone.utc)
    assert p.should_refresh(now) is True

    # not yet reached interval
    latest = datetime(2022, 1, 2, 14, 1, 30, tzinfo=timezone.utc)
    p = make_plugin(refresh={"interval": 120}, latest_refresh_time=latest.isoformat())
    now = datetime(2022, 1, 2, 14, 2, 0, tzinfo=timezone.utc)
    assert p.should_refresh(now) is False


def test_scheduled_refresh_when_latest_refresh_varies():
    # latest refresh earlier same day before scheduled -> should refresh when current is at scheduled
    latest = datetime(2022, 1, 2, 14, 0, 0)
    p = make_plugin(refresh={"scheduled": "15:00"}, latest_refresh_time=latest.isoformat())
    now = datetime(2022, 1, 2, 15, 0, 0)
    assert p.should_refresh(now) is True

    # latest refresh on same day after scheduled -> should not refresh
    latest = datetime(2022, 1, 2, 15, 30, 0)
    p = make_plugin(refresh={"scheduled": "15:00"}, latest_refresh_time=latest.isoformat())
    now = datetime(2022, 1, 2, 16, 0, 0)
    assert p.should_refresh(now) is False

    # latest refresh previous day -> should refresh at scheduled time today
    latest = datetime(2022, 1, 1, 23, 59, 0)
    p = make_plugin(refresh={"scheduled": "08:00"}, latest_refresh_time=latest.isoformat())
    now = datetime(2022, 1, 2, 8, 0, 0)
    assert p.should_refresh(now) is True


def test_never_refreshed_scheduled_with_tz_aware_current_time():
    # when current_time is timezone-aware we should not raise and should compare correctly
    p = make_plugin(refresh={"scheduled": "14:00"})
    now = datetime(2022, 1, 2, 14, 0, 0, tzinfo=timezone.utc)
    assert p.should_refresh(now) is True

    now = datetime(2022, 1, 2, 13, 59, 0, tzinfo=timezone.utc)
    assert p.should_refresh(now) is False


def test_scheduled_refresh_timezone_aware_latest_and_current():
    # both latest and current are timezone-aware
    latest = datetime(2022, 1, 1, 23, 59, 0, tzinfo=timezone.utc)
    p = make_plugin(refresh={"scheduled": "08:00"}, latest_refresh_time=latest.isoformat())
    now = datetime(2022, 1, 2, 8, 0, 0, tzinfo=timezone.utc)
    assert p.should_refresh(now) is True
