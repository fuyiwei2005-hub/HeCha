from app.services.pest_names import CLASS_CN, to_chinese


def test_known_class_is_translated():
    """模型主要虫种必须能翻译成中文"""
    assert to_chinese("aphids") == "蚜虫"
    assert to_chinese("Icerya purchasi Maskell") == "吹绵蚧"
    assert to_chinese("blister beetle") == "斑蝥"


def test_unknown_class_falls_back_to_original():
    """未收录的类别原样返回英文，不得报错或返回空"""
    assert to_chinese("some new pest") == "some new pest"
    assert to_chinese("") == ""


def test_mapping_is_complete_and_valid():
    """映射表覆盖模型全部 46 类，且无空值/重复中文名"""
    assert len(CLASS_CN) == 46
    assert all(k.strip() for k in CLASS_CN)
    assert all(v.strip() for v in CLASS_CN.values())
    # 中文名唯一，避免不同虫种显示成同一个名字
    assert len(set(CLASS_CN.values())) == len(CLASS_CN)
