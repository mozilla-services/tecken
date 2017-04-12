from tecken.dockerflow_extra import check_redis_store_connected


def test_check_redis_store_connected_happy_path():
    assert not check_redis_store_connected(None)
