"""安装时写入的内置示例：对话角色与图像提示词模板。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from .models import PromptTemplate

ROLES = [
    ("✍️", "文案策划", "你是一名资深新媒体文案策划，擅长小红书、公众号、短视频脚本的写作。"
     "根据用户给出的主题，先确认目标人群与平台，再给出 3 个不同风格的标题和正文，语言生动、有记忆点，适度使用 emoji。"),
    ("🎬", "分镜编剧", "你是一名短片编剧兼分镜师。根据用户的故事梗概，输出：1) 一句话 logline；2) 分场大纲；"
     "3) 分镜表（镜号、景别、画面描述、台词/旁白、时长）。画面描述要可以直接用作 AI 绘图 / 视频提示词。"),
    ("🎨", "绘画提示词专家", "你是 AI 绘画提示词专家。用户描述想要的画面后，输出中文和英文两版高质量提示词，"
     "包含主体、细节、环境、构图、光影、风格、画质关键词，并附一行反向提示词。"),
    ("🌐", "中英翻译", "你是专业译者。用户输入中文时翻译为地道的英文，输入其他语言时翻译为流畅的简体中文。"
     "保持原文格式，专有名词保留原文，只输出译文。"),
    ("🧠", "头脑风暴", "你是创意顾问。针对用户的主题，从不同角度给出至少 10 个有新意的点子，每个点子一句话说明亮点，"
     "最后挑出你最推荐的 3 个并说明理由。"),
]

IMAGE_PROMPTS = [
    ("🌆", "赛博朋克城市", "雨夜的赛博朋克城市街道，霓虹灯招牌倒映在湿漉漉的路面上，飞行汽车穿梭在高楼之间，"
     "电影感构图，蓝紫色调，体积光，超高细节，8k", "模糊, 低质量, 变形, 水印, 文字"),
    ("🏮", "国风山水", "水墨国风山水画，云雾缭绕的青山，一叶扁舟行于江上，远处有亭台楼阁，留白构图，淡雅色彩，宣纸质感",
     "现代建筑, 照片, 低质量"),
    ("📷", "人像写真", "窗边自然光下的人像写真，柔和侧光，浅景深虚化背景，胶片质感，温暖色调，85mm 镜头，细腻肤质",
     "畸形手指, 多余肢体, 过度磨皮, 低质量"),
    ("🧸", "3D 可爱角色", "一只圆滚滚的小熊 3D 角色，皮克斯风格，柔软毛绒质感，大眼睛，站在糖果色背景前，柔和打光，C4D 渲染，高清",
     "恐怖, 低质量, 噪点"),
    ("🍜", "美食摄影", "一碗热气腾腾的红烧牛肉面，俯拍角度，木质桌面，旁边点缀葱花和辣椒，商业美食摄影，自然光，诱人色泽",
     "模糊, 过曝, 低质量"),
]


def seed_defaults(db: Session) -> None:
    from .site import set_setting

    set_setting(db, "builtin_seeded", True)
    for icon, title, content in ROLES:
        db.add(PromptTemplate(title=title, category="chat", icon=icon, content=content))
    for icon, title, content, negative in IMAGE_PROMPTS:
        db.add(PromptTemplate(title=title, category="image", icon=icon, content=content, negative=negative))


def seed_if_upgraded(db: Session) -> None:
    """从旧版本升级的实例补充一次内置示例（只执行一次，用户删除后不会再加回来）。"""
    from .site import get_setting, is_installed

    if is_installed(db) and not get_setting(db, "builtin_seeded"):
        seed_defaults(db)
        db.commit()
