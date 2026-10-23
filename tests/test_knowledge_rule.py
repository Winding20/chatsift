from app.feed_generator import _knowledge_ok


def test_vague_short_quote_is_rejected():
    assert _knowledge_ok({}, "拍照耗电") is False


def test_pure_evaluation_is_rejected():
    assert _knowledge_ok({"reusable": True}, "两边都打得好傻逼") is False


def test_self_marked_reusable_is_accepted():
    assert _knowledge_ok({"reusable": True}, "镜像的话自己挂个cdn 买个服务器") is True


def test_self_marked_not_reusable_is_rejected():
    assert _knowledge_ok({"reusable": False}, "K90 max 风扇比拯救者还大") is False


def test_missing_flag_needs_concrete_object():
    assert _knowledge_ok({}, "新手机在光照好的情况下都很清楚吧其实") is False
    assert _knowledge_ok({}, "K90 max 风扇比拯救者还大") is True
