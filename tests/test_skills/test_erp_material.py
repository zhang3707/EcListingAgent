"""ERP 素材检索 Skill 测试（mock 客户端）。"""
import asyncio

from skills.erp_material import ErpMaterialSkill


class _Cfg:
    erp = {"mock": True}


def test_erp_material_mock_ok():
    skill = ErpMaterialSkill(config=_Cfg())
    res = asyncio.run(skill.execute(product_code="P100001"))
    assert res.ok
    material = res.data["material"]
    assert "title" in material
    assert "image_urls" in material
    assert isinstance(material["skus"], list)
    assert len(material["skus"]) >= 1
