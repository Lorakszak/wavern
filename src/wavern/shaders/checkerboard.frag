#version 330 core

in vec2 v_texcoord;
out vec4 fragColor;

uniform float u_tile_size;

void main() {
    vec2 tile = floor(v_texcoord / u_tile_size);
    float checker = mod(tile.x + tile.y, 2.0);
    fragColor = mix(vec4(0.60, 0.60, 0.60, 1.0),
                    vec4(0.80, 0.80, 0.80, 1.0), checker);
}
