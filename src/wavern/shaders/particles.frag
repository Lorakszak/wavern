#version 330 core

in vec3 v_color;
in float v_alpha;

out vec4 fragColor;

void main() {
    // Circular point with soft edges
    vec2 coord = gl_PointCoord * 2.0 - 1.0;
    float dist = length(coord);

    if (dist > 1.0) {
        discard;
    }

    float alpha = v_alpha * (1.0 - smoothstep(0.5, 1.0, dist));
    fragColor = vec4(v_color, alpha);
}
