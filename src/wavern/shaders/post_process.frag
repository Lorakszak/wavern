#version 330 core

uniform sampler2D u_texture;
uniform float u_bloom_intensity;
uniform float u_bloom_radius;
uniform vec2 u_resolution;

in vec2 v_texcoord;
out vec4 fragColor;

void main() {
    vec4 color = texture(u_texture, v_texcoord);

    if (u_bloom_intensity > 0.01) {
        vec4 bloom = vec4(0.0);
        float total_weight = 0.0;
        int samples = 8;
        float radius = u_bloom_radius / u_resolution.x;

        for (int x = -samples; x <= samples; x++) {
            for (int y = -samples; y <= samples; y++) {
                vec2 offset = vec2(float(x), float(y)) * radius / float(samples);
                float weight = 1.0 - length(vec2(float(x), float(y))) / float(samples);
                weight = max(weight, 0.0);
                weight *= weight;
                bloom += texture(u_texture, v_texcoord + offset) * weight;
                total_weight += weight;
            }
        }

        bloom /= total_weight;
        color += bloom * u_bloom_intensity;
    }

    fragColor = color;
}
