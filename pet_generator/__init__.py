"""desktop-pet-gen — AI 驱动的桌面宠物精灵动画生成管线。

将单张宠物图片通过 AI 管线转化为可交互的桌面宠物精灵动画：
    图片 → 标准化 → 姿态生成 → 视频生成 → 帧提取 → 去背景 → 精灵图打包 → Rust 运行时

核心模块:
    config: 聚合配置中心
    providers: AI 服务抽象层（图像生成、视频生成、视觉理解）
    stages: 管线各阶段实现（由其他模块负责）
"""

__version__ = "0.1.0"
__app_name__ = "desktop-pet-gen"
