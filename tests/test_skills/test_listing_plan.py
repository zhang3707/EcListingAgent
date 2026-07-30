"""上架计划构建（build_listing_plan）纯逻辑测试。"""
from skills.listing import build_listing_plan


def _material():
    return {
        "title": "测试商品标题" * 20,            # 超长，验证截断
        "image_urls": ["http://x/a.jpg", "http://x/b.jpg"],
        "spec_params": {"品牌": "示例", "产地": "中国"},
        "detail_text": "详情描述文本",
        "skus": [{"sku_code": "S1", "spec": "红-M", "cost": 50, "stock": 10}],
    }


def _listing_cfg():
    return {
        "publish_path": "/item/publish",
        "list_path": "/item/list",
        "category": {"selector": "#cat", "value": "服装/男装/T恤"},
        "fields": {
            "title": {"selector": "input[name=title]", "type": "input", "max": 60},
            "sellpoint": {"selector": "textarea[name=sellpoint]", "type": "textarea", "max": 140},
            "detail": {"selector": "textarea[name=detail]", "type": "textarea"},
            "image_upload": {
                "main": {"selector": "input[type=file]", "multiple": True},
                "detail": {"selector": ".detail-upload input[type=file]"},
            },
        },
        "sku": {"add_spec_btn": "#addSku", "price": "input.sku-price", "stock": "input.sku-stock"},
        "shipping": {"selector": "#ship", "value": "默认运费模板"},
        "submit_btn": "button.submit",
        "list_verify": {"item_row": ".item-row", "success_status": "上架中"},
    }


def test_plan_text_fields_and_truncation():
    plan = build_listing_plan(_material(), [{"sku": "S1", "price": 67.5, "stock": 10}],
                              _listing_cfg())
    tf = {f["selector"]: f for f in plan["text_fields"]}
    # 标题被截断到 60 字
    assert len(tf["input[name=title]"]["value"]) == 60
    # 卖点由 spec_params 派生
    assert "品牌:示例" in tf["textarea[name=sellpoint]"]["value"]
    assert "产地:中国" in tf["textarea[name=sellpoint]"]["value"]
    # 详情
    assert tf["textarea[name=detail]"]["value"] == "详情描述文本"


def test_plan_images():
    plan = build_listing_plan(_material(), [], _listing_cfg())
    imgs = {i["selector"]: i for i in plan["images"]}
    assert imgs["input[type=file]"]["multiple"] is True
    assert len(imgs["input[type=file]"]["urls"]) == 2
    # detail 未声明 multiple，默认 False
    assert imgs[".detail-upload input[type=file]"]["multiple"] is False


def test_plan_skus_and_misc():
    skus = [{"sku": "S1", "price": 67.5, "stock": 10, "spec": "红-M"}]
    plan = build_listing_plan(_material(), skus, _listing_cfg())
    assert plan["skus"] == skus
    assert plan["category"]["value"] == "服装/男装/T恤"
    assert plan["shipping"]["value"] == "默认运费模板"
    assert plan["submit"] == "button.submit"
    assert plan["list_verify"]["success_status"] == "上架中"


def test_plan_missing_fields_graceful():
    """缺少字段配置时不应报错，仅跳过。"""
    plan = build_listing_plan({"title": "T"}, [], {"submit_btn": "button"})
    assert plan["text_fields"] == []
    assert plan["images"] == []
    assert plan["category"] is None
    assert plan["shipping"] is None


def test_sellpoint_override():
    """material 自带 sellpoint 时优先使用。"""
    mat = _material()
    mat["sellpoint"] = "自定义卖点"
    plan = build_listing_plan(mat, [], _listing_cfg())
    tf = {f["selector"]: f for f in plan["text_fields"]}
    assert tf["textarea[name=sellpoint]"]["value"] == "自定义卖点"
