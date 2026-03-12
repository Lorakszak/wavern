#version 330 core

uniform float u_magnitudes[128];
uniform int u_bar_count;
uniform float u_inner_radius;
uniform float u_bar_length;
uniform vec3 u_colors[8];
uniform int u_color_count;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_rotation_speed;
uniform float u_amplitude;
uniform float u_bar_width_ratio;
uniform float u_glow_intensity;
uniform float u_rotation_offset;
uniform vec2 u_center_offset;
uniform float u_viz_scale;

in vec2 v_texcoord;
out vec4 fragColor;

#define PI 3.14159265359

vec3 get_color(float t) {
    if (u_color_count <= 1) {
        return u_colors[0];
    }
    float idx_f = t * float(u_color_count - 1);
    int idx = int(floor(idx_f));
    float fract_t = idx_f - float(idx);
    idx = clamp(idx, 0, u_color_count - 2);
    return mix(u_colors[idx], u_colors[idx + 1], fract_t);
}

void main() {
    // Center UV coordinates and correct aspect ratio
    vec2 uv = v_texcoord * 2.0 - 1.0;
    float aspect = u_resolution.x / u_resolution.y;
    uv.x *= aspect;

    // Apply center offset
    uv -= u_center_offset;

    // Apply scale to radii
    float scaled_inner = u_inner_radius * u_viz_scale;
    float scaled_bar_length = u_bar_length * u_viz_scale;

    float dist = length(uv);
    float angle = atan(uv.y, uv.x) + PI; // [0, 2PI]

    // Apply rotation (dynamic + static offset)
    angle = mod(angle + u_time * u_rotation_speed + u_rotation_offset, 2.0 * PI);

    // Map angle to bar index
    float bar_angle = 2.0 * PI / float(u_bar_count);
    int bar_idx = int(floor(angle / bar_angle));
    bar_idx = clamp(bar_idx, 0, u_bar_count - 1);

    float bar_center_angle = (float(bar_idx) + 0.5) * bar_angle;
    float angle_diff = abs(angle - bar_center_angle);

    // Bar width (angular)
    float bar_angular_width = bar_angle * u_bar_width_ratio;

    if (angle_diff > bar_angular_width * 0.5) {
        fragColor = vec4(0.0);
        return;
    }

    float magnitude = u_magnitudes[bar_idx];
    float outer_radius = scaled_inner + magnitude * scaled_bar_length;

    if (dist >= scaled_inner && dist <= outer_radius) {
        float t = (dist - scaled_inner) / (outer_radius - scaled_inner);
        float bar_pos = float(bar_idx) / float(u_bar_count);
        vec3 color = get_color(bar_pos);

        // Fade at edges
        float edge_fade = 1.0 - smoothstep(bar_angular_width * 0.3, bar_angular_width * 0.5, angle_diff);
        float intensity = (0.7 + 0.3 * t) * edge_fade;

        // Glow at tips
        float tip_glow = smoothstep(0.8, 1.0, t) * magnitude * u_glow_intensity;
        color += tip_glow;

        fragColor = vec4(color * intensity, 1.0);
    } else if (dist < scaled_inner && dist > scaled_inner - 0.005) {
        // Inner ring glow
        float ring_glow = u_amplitude * u_glow_intensity * 0.6;
        vec3 color = get_color(angle / (2.0 * PI));
        fragColor = vec4(color * ring_glow, ring_glow);
    } else {
        fragColor = vec4(0.0);
    }
}
