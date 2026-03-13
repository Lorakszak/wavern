#version 330 core

uniform float u_magnitudes[128];
uniform int u_bar_count;
uniform float u_inner_size;
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
uniform int u_mirror_sides;

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

// Check one side of the rectangle and return (hit, color, alpha).
// side_pos: position along the side [0,1], side_dist: signed distance from side edge (positive = outward)
vec4 render_side(float side_pos, float side_dist, int bar_offset, int bars_per_side, bool reverse) {
    if (side_dist < 0.0) return vec4(0.0);

    float bar_slot = 1.0 / float(bars_per_side);
    int local_idx = int(floor(side_pos / bar_slot));
    local_idx = clamp(local_idx, 0, bars_per_side - 1);

    // Mirror mode: fold spectrum so bass (low indices) peaks at center,
    // high frequencies at both corners — symmetric per side.
    // Normal mode: full spectrum per side, clockwise ordering ensures
    // adjacent sides have complementary ends at each corner.
    int mag_idx;
    if (u_mirror_sides == 1) {
        int half = bars_per_side / 2;
        int dist_from_center = abs(local_idx - half);
        mag_idx = dist_from_center;
    } else {
        // Reverse on alternating sides so each corner has bass meeting treble
        mag_idx = reverse ? (bars_per_side - 1 - local_idx) : local_idx;
    }
    int bar_idx = clamp(mag_idx, 0, u_bar_count - 1);

    float bar_center = (float(local_idx) + 0.5) * bar_slot;
    float pos_diff = abs(side_pos - bar_center);
    float bar_width = bar_slot * u_bar_width_ratio;

    if (pos_diff > bar_width * 0.5) return vec4(0.0);

    float magnitude = u_magnitudes[bar_idx];
    float max_extent = magnitude * u_bar_length * u_viz_scale;

    if (side_dist > max_extent) return vec4(0.0);

    float t = side_dist / max(max_extent, 0.001);
    float bar_pos = float(bar_idx) / float(u_bar_count);
    vec3 color = get_color(bar_pos);

    float edge_fade = 1.0 - smoothstep(bar_width * 0.3, bar_width * 0.5, pos_diff);
    float intensity = (0.7 + 0.3 * t) * edge_fade;

    float tip_glow = smoothstep(0.8, 1.0, t) * magnitude * u_glow_intensity;
    color += tip_glow;

    return vec4(color * intensity, 1.0);
}

void main() {
    vec2 uv = v_texcoord * 2.0 - 1.0;
    float aspect = u_resolution.x / u_resolution.y;
    uv.x *= aspect;

    // Apply center offset
    uv -= u_center_offset;

    // Apply rotation
    float rot_angle = u_time * u_rotation_speed + u_rotation_offset;
    float c = cos(rot_angle), s = sin(rot_angle);
    uv = mat2(c, s, -s, c) * uv;

    float sz = u_inner_size * u_viz_scale;

    // Every side always shows the full spectrum
    int bars_per_side = u_bar_count;
    if (bars_per_side < 1) bars_per_side = 1;

    // Classify which side this pixel belongs to by checking all four.
    // Each side is a strip extending outward from one edge of the square.
    // Right side: x in [sz, sz + bar_length], y in [-sz, sz]
    // Top side:   y in [sz, sz + bar_length], x in [-sz, sz]
    // Left side:  x in [-sz - bar_length, -sz], y in [-sz, sz]
    // Bottom:     y in [-sz - bar_length, -sz], x in [-sz, sz]

    float max_bar_ext = u_bar_length * u_viz_scale;

    // Right side (reversed so bass is at top, treble at bottom)
    if (uv.x >= sz && uv.x <= sz + max_bar_ext && uv.y >= -sz && uv.y <= sz) {
        float side_pos = (uv.y + sz) / (2.0 * sz);
        float side_dist = uv.x - sz;
        vec4 result = render_side(side_pos, side_dist, 0, bars_per_side, true);
        if (result.a > 0.0) { fragColor = result; return; }
    }

    // Top side (normal: bass at left, treble at right)
    if (uv.y >= sz && uv.y <= sz + max_bar_ext && uv.x >= -sz && uv.x <= sz) {
        float side_pos = (uv.x + sz) / (2.0 * sz);
        float side_dist = uv.y - sz;
        vec4 result = render_side(side_pos, side_dist, 0, bars_per_side, false);
        if (result.a > 0.0) { fragColor = result; return; }
    }

    // Left side (reversed so bass is at bottom, treble at top)
    if (uv.x <= -sz && uv.x >= -sz - max_bar_ext && uv.y >= -sz && uv.y <= sz) {
        float side_pos = (-uv.y + sz) / (2.0 * sz);
        float side_dist = -uv.x - sz;
        vec4 result = render_side(side_pos, side_dist, 0, bars_per_side, true);
        if (result.a > 0.0) { fragColor = result; return; }
    }

    // Bottom side (normal: bass at right, treble at left)
    if (uv.y <= -sz && uv.y >= -sz - max_bar_ext && uv.x >= -sz && uv.x <= sz) {
        float side_pos = (-uv.x + sz) / (2.0 * sz);
        float side_dist = -uv.y - sz;
        vec4 result = render_side(side_pos, side_dist, 0, bars_per_side, false);
        if (result.a > 0.0) { fragColor = result; return; }
    }

    // Inner edge glow (pixels just inside the square boundary)
    float dx = abs(uv.x) - sz;
    float dy = abs(uv.y) - sz;
    float edge_dist;
    if (abs(uv.x) <= sz && abs(uv.y) <= sz) {
        // Inside the square: distance to nearest edge (negative)
        edge_dist = -min(sz - abs(uv.x), sz - abs(uv.y));
    } else {
        edge_dist = 1.0;  // outside, skip glow
    }

    if (edge_dist > -0.008 * u_viz_scale && edge_dist <= 0.0) {
        float glow_t = 1.0 + edge_dist / (0.008 * u_viz_scale);
        float ring_glow = u_amplitude * u_glow_intensity * 0.6 * glow_t;
        // Color based on which edge we're nearest to
        float perim;
        if (sz - abs(uv.x) < sz - abs(uv.y)) {
            perim = (uv.x > 0.0) ? 0.125 : 0.625;
        } else {
            perim = (uv.y > 0.0) ? 0.375 : 0.875;
        }
        vec3 color = get_color(perim);
        fragColor = vec4(color * ring_glow, ring_glow);
        return;
    }

    fragColor = vec4(0.0);
}
