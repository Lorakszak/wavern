#version 330 core

uniform float u_magnitudes[256];
uniform int u_bar_count;
uniform float u_inner_size;
uniform float u_bar_length;
uniform vec3 u_colors[8];
uniform int u_color_count;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_rotation_speed;
uniform float u_amplitude;
uniform float u_bar_spacing;
uniform float u_glow_intensity;
uniform float u_rotation_offset;
uniform vec2 u_center_offset;
uniform float u_viz_scale;
uniform int u_mirror_sides;
uniform int u_mirror_half;
uniform float u_bar_roundness;

uniform int u_shadow_enabled;
uniform vec3 u_shadow_color;
uniform float u_shadow_opacity;
uniform vec2 u_shadow_offset;
uniform float u_shadow_size;
uniform float u_shadow_blur;

uniform sampler2D u_image_tex;
uniform int u_image_enabled;
uniform float u_image_padding;
uniform float u_image_bounce;
uniform int u_image_bounce_zoom;
uniform float u_shape_bounce;

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
// size_scale stretches bar extent for shadow sizing.
vec4 render_side(float side_pos, float side_dist, int bars_per_side, bool reverse, float size_scale) {
    if (side_dist < 0.0) return vec4(0.0);

    float bar_slot = 1.0 / float(bars_per_side);
    int local_idx = int(floor(side_pos / bar_slot));
    local_idx = clamp(local_idx, 0, bars_per_side - 1);

    int mag_idx;
    if (u_mirror_sides == 1) {
        int half = bars_per_side / 2;
        int dist_from_center = abs(local_idx - half);
        if (u_mirror_half == 0) {
            mag_idx = dist_from_center;                   // bass at center
        } else {
            mag_idx = (half - 1 - dist_from_center);     // treble at center
        }
    } else {
        mag_idx = reverse ? (bars_per_side - 1 - local_idx) : local_idx;
    }
    int bar_idx = clamp(mag_idx, 0, u_bar_count - 1);

    float bar_center = (float(local_idx) + 0.5) * bar_slot;
    float pos_diff = abs(side_pos - bar_center);
    float bar_width = bar_slot * (1.0 - u_bar_spacing);

    if (pos_diff > bar_width * 0.5) return vec4(0.0);

    float magnitude = u_magnitudes[bar_idx];
    float max_extent = magnitude * u_bar_length * u_viz_scale * size_scale;

    if (side_dist > max_extent) return vec4(0.0);

    // Bar roundness
    float half_w = bar_width * 0.5;
    float r = u_bar_roundness * half_w;
    if (r > 0.0 && side_dist > max_extent - r) {
        float dy = side_dist - (max_extent - r);
        if (pos_diff * pos_diff + dy * dy > r * r) return vec4(0.0);
    }

    float t = side_dist / max(max_extent, 0.001);
    float bar_pos = float(local_idx) / float(bars_per_side);
    vec3 color = get_color(bar_pos);

    float edge_fade = 1.0 - smoothstep(bar_width * 0.3, bar_width * 0.5, pos_diff);
    float intensity = (0.7 + 0.3 * t) * edge_fade;

    float tip_glow = smoothstep(0.8, 1.0, t) * magnitude * u_glow_intensity;
    color += tip_glow;

    return vec4(color * intensity, 1.0);
}

// Try all four sides and return the first hit.
vec4 compute_all_sides(vec2 uv, float size_scale) {
    float sz = u_inner_size * u_viz_scale * (1.0 + u_shape_bounce);
    int bars_per_side = u_bar_count;
    if (bars_per_side < 1) bars_per_side = 1;
    float max_bar_ext = u_bar_length * u_viz_scale * size_scale;

    // Right side
    if (uv.x >= sz && uv.x <= sz + max_bar_ext && uv.y >= -sz && uv.y <= sz) {
        float side_pos = (uv.y + sz) / (2.0 * sz);
        float side_dist = uv.x - sz;
        vec4 result = render_side(side_pos, side_dist, bars_per_side, true, size_scale);
        if (result.a > 0.0) return result;
    }

    // Top side
    if (uv.y >= sz && uv.y <= sz + max_bar_ext && uv.x >= -sz && uv.x <= sz) {
        float side_pos = (uv.x + sz) / (2.0 * sz);
        float side_dist = uv.y - sz;
        vec4 result = render_side(side_pos, side_dist, bars_per_side, false, size_scale);
        if (result.a > 0.0) return result;
    }

    // Left side
    if (uv.x <= -sz && uv.x >= -sz - max_bar_ext && uv.y >= -sz && uv.y <= sz) {
        float side_pos = (-uv.y + sz) / (2.0 * sz);
        float side_dist = -uv.x - sz;
        vec4 result = render_side(side_pos, side_dist, bars_per_side, true, size_scale);
        if (result.a > 0.0) return result;
    }

    // Bottom side
    if (uv.y <= -sz && uv.y >= -sz - max_bar_ext && uv.x >= -sz && uv.x <= sz) {
        float side_pos = (-uv.x + sz) / (2.0 * sz);
        float side_dist = -uv.y - sz;
        vec4 result = render_side(side_pos, side_dist, bars_per_side, false, size_scale);
        if (result.a > 0.0) return result;
    }

    return vec4(0.0);
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

    float sz = u_inner_size * u_viz_scale * (1.0 + u_shape_bounce);

    // Shadow pass
    if (u_shadow_enabled == 1) {
        vec2 shadow_uv = uv - u_shadow_offset;
        vec4 shadow_bar = compute_all_sides(shadow_uv, u_shadow_size);
        if (shadow_bar.a > 0.0) {
            float alpha = shadow_bar.a * u_shadow_opacity;
            if (u_shadow_blur > 0.0) {
                float edge_sum = 0.0;
                float samples = 0.0;
                for (float dx = -1.0; dx <= 1.0; dx += 1.0) {
                    for (float dy = -1.0; dy <= 1.0; dy += 1.0) {
                        vec2 s_uv = shadow_uv + vec2(dx, dy) * u_shadow_blur;
                        edge_sum += compute_all_sides(s_uv, u_shadow_size).a;
                        samples += 1.0;
                    }
                }
                alpha = (edge_sum / samples) * u_shadow_opacity;
            }
            fragColor = vec4(u_shadow_color * alpha, alpha);
        } else {
            fragColor = vec4(0.0);
        }
    } else {
        fragColor = vec4(0.0);
    }

    // Bar pass
    vec4 bar = compute_all_sides(uv, 1.0);
    if (bar.a > 0.0) {
        fragColor = bar;
        return;
    }

    // Inner image (inside square)
    if (abs(uv.x) < sz && abs(uv.y) < sz) {
        if (u_image_enabled == 1) {
            float base_sz = sz * (1.0 - u_image_padding);
            float display_sz = base_sz * (1.0 + u_image_bounce);
            // Scale mode: UV uses base_sz (image stretches to fill)
            // Zoom mode: UV uses display_sz (image reveals more content)
            float uv_sz = (u_image_bounce_zoom == 1) ? display_sz : base_sz;

            if (abs(uv.x) < display_sz && abs(uv.y) < display_sz && display_sz > 0.0) {
                vec2 img_uv = uv / uv_sz * 0.5 + 0.5;

                // Cover mode aspect correction
                vec2 tex_size = vec2(textureSize(u_image_tex, 0));
                float img_aspect = tex_size.x / tex_size.y;
                if (img_aspect > 1.0) {
                    img_uv.x = (img_uv.x - 0.5) / img_aspect + 0.5;
                } else {
                    img_uv.y = (img_uv.y - 0.5) * img_aspect + 0.5;
                }

                if (img_uv.x >= 0.0 && img_uv.x <= 1.0 &&
                    img_uv.y >= 0.0 && img_uv.y <= 1.0) {
                    fragColor = texture(u_image_tex, img_uv);
                }
            }
        }
    }

    // Inner edge glow (only if no bar hit)
    if (fragColor.a > 0.0) return;  // shadow already set

    float dx = abs(uv.x) - sz;
    float dy = abs(uv.y) - sz;
    float edge_dist;
    if (abs(uv.x) <= sz && abs(uv.y) <= sz) {
        edge_dist = -min(sz - abs(uv.x), sz - abs(uv.y));
    } else {
        edge_dist = 1.0;
    }

    if (edge_dist > -0.008 * u_viz_scale && edge_dist <= 0.0) {
        float glow_t = 1.0 + edge_dist / (0.008 * u_viz_scale);
        float ring_glow = u_amplitude * u_glow_intensity * 0.6 * glow_t;
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
}
