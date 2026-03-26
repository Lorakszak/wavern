#version 330 core

in vec2 v_uv;
out vec4 frag_color;

// Max 7 layers
uniform int u_layer_count;
uniform sampler2D u_layers[7];
uniform float u_opacities[7];
uniform int u_blend_modes[7];
uniform int u_visible[7];

vec4 blend_normal(vec4 dst, vec4 src) {
    return vec4(src.rgb + dst.rgb * (1.0 - src.a), src.a + dst.a * (1.0 - src.a));
}

vec4 blend_additive(vec4 dst, vec4 src) {
    return vec4(dst.rgb + src.rgb * src.a, max(dst.a, src.a));
}

vec4 blend_screen(vec4 dst, vec4 src) {
    return vec4(1.0 - (1.0 - dst.rgb) * (1.0 - src.rgb * src.a), max(dst.a, src.a));
}

vec4 blend_multiply(vec4 dst, vec4 src) {
    return vec4(dst.rgb * mix(vec3(1.0), src.rgb, src.a), max(dst.a, src.a));
}

void main() {
    vec4 result = vec4(0.0);

    for (int i = 0; i < u_layer_count; i++) {
        if (u_visible[i] == 0) continue;

        vec4 src = texture(u_layers[i], v_uv);
        src.a *= u_opacities[i];

        if (u_blend_modes[i] == 0)      result = blend_normal(result, src);
        else if (u_blend_modes[i] == 1)  result = blend_additive(result, src);
        else if (u_blend_modes[i] == 2)  result = blend_screen(result, src);
        else if (u_blend_modes[i] == 3)  result = blend_multiply(result, src);
    }

    frag_color = result;
}
