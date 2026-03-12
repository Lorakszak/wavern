"""Shader loading utilities."""

from importlib import resources


def load_shader(name: str) -> str:
    """Load a shader source file from the shaders package.

    Args:
        name: Filename of the shader (e.g. "common.vert", "waveform.frag").

    Returns:
        Shader source code as a string.

    Raises:
        FileNotFoundError: If the shader file does not exist.
    """
    shader_dir = resources.files("wavern.shaders")
    shader_file = shader_dir.joinpath(name)
    return shader_file.read_text(encoding="utf-8")
