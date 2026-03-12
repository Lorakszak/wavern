#version 330 core

in vec2 v_texcoord;
out vec4 fragColor;

uniform sampler2D u_background;

void main() {
    fragColor = texture(u_background, v_texcoord);
}
