"""害虫类别英文 -> 中文名映射。

类别清单来自项目自带权重 `model_weights/best.pt` 的 `YOLO(...).names`（共 46 类）。
新增字段 `class_cn` 会随检测结果一起返回并入库，供前端与报告直接显示中文，
避免演示时向评委展示纯英文虫种名。未命中的类别原样返回英文，不会报错。
"""

# key 必须与模型输出的英文类别名完全一致（区分大小写）
CLASS_CN: dict[str, str] = {
    "rice leaf roller": "稻纵卷叶螟",
    "rice gall midge": "稻瘿蚊",
    "rice water weevil": "稻水象甲",
    "grub": "蛴螬",
    "mole cricket": "蝼蛄",
    "wireworm": "金针虫",
    "black cutworm": "小地老虎",
    "red spider": "红蜘蛛",
    "corn borer": "玉米螟",
    "aphids": "蚜虫",
    "Potosiabre vitarsis": "白星花金龟",
    "peach borer": "桃蛀螟",
    "penthaleus major": "麦圆叶爪螨",
    "longlegged spider mite": "长腿红蜘蛛",
    "wheat phloeothrips": "小麦管蓟马",
    "wheat sawfly": "麦叶蜂",
    "beet fly": "甜菜潜叶蝇",
    "flea beetle": "黄曲条跳甲",
    "Locustoidea": "蝗虫",
    "legume blister beetle": "豆芫菁",
    "blister beetle": "斑蝥",
    "Thrips": "蓟马",
    "Viteus vitifoliae": "葡萄根瘤蚜",
    "Colomerus vitis": "葡萄瘿螨",
    "oides decempunctata": "十星瓢萤叶甲",
    "Polyphagotars onemus latus": "侧多食跗线螨",
    "Pseudococcus comstocki Kuwana": "康氏粉蚧",
    "parathrene regalis": "葡萄透翅蛾",
    "Ampelophaga": "葡萄天蛾",
    "Lycorma delicatula": "斑衣蜡蝉",
    "Xylotrechus": "葡萄虎天牛",
    "Cicadella viridis": "大青叶蝉",
    "Miridae": "盲蝽",
    "Phyllocoptes oleiverus ashmead": "柑橘锈螨",
    "Icerya purchasi Maskell": "吹绵蚧",
    "Unaspis yanonensis": "矢尖蚧",
    "Ceroplastes rubens": "红蜡蚧",
    "Parlatoria zizyphus Lucus": "黑点蚧",
    "Dacus dorsalis(Hendel)": "橘小实蝇",
    "Prodenia litura": "斜纹夜蛾",
    "Adristyrannus": "枯叶夜蛾",
    "Phyllocnistis citrella Stainton": "柑橘潜叶蛾",
    "Lawana imitata Melichar": "白蛾蜡蝉",
    "Salurnis marginella Guerr": "褐缘蛾蜡蝉",
    "Rhytidodera bowrinii white": "皱胸天牛",
    "Cicadellidae": "叶蝉",
}


def to_chinese(name: str) -> str:
    """把模型输出的英文类别名转成中文；未收录时原样返回。"""
    return CLASS_CN.get(name, name)
