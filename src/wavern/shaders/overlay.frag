#version 330 core

in vec2 v_texcoord;
out vec4 fragColor;

uniform sampler2D u_overlay;
uniform float u_opacity;

// Transform uniforms
uniform float u_rotation;       // rotation in radians
uniform int u_mirror_x;         // 1 = mirror horizontally
uniform int u_mirror_y;         // 1 = mirror vertically

vec2 apply_rotation(vec2 uv, float angle) {
    if (angle == 0.0) return uv;
    vec2 center = vec2(0.5);
    uv -= center;
    float c = cos(angle);
    float s = sin(angle);
    uv = vec2(uv.x * c - uv.y * s, uv.x * s + uv.y * c);
    uv += center;
    return uv;
}

vec2 apply_mirror(vec2 uv) {
    if (u_mirror_x == 1) uv.x = 1.0 - uv.x;
    if (u_mirror_y == 1) uv.y = 1.0 - uv.y;
    return uv;
}

void main() {
    vec2 uv = v_texcoord;
    uv = apply_rotation(uv, u_rotation);
    uv = apply_mirror(uv);
    vec4 color = texture(u_overlay, uv);
    color.a *= u_opacity;
    fragColor = color;
}
