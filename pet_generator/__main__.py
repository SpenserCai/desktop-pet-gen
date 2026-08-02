"""python -m pet_generator 入口。

允许通过 ``python -m pet_generator`` 直接运行管线 CLI，
等价于 ``pet-gen`` 命令（pyproject.toml 中定义的 console_scripts）。
"""

from pet_generator.cli import main

if __name__ == "__main__":
    main()
