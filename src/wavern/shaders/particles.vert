#version 330 core

in vec2 in_position;
in float in_size;
in vec3 in_color;
in float in_alpha;

out vec3 v_color;
out float v_alpha;

void main() {
    gl_Position = vec4(in_position * 2.0 - 1.0, 0.0, 1.0);
    gl_PointSize = in_size;
    v_color = in_color;
    v_alpha = in_alpha;
}
