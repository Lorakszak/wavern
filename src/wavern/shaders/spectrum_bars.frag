#version 330 core

uniform float u_magnitudes[256];
uniform int u_bar_count;
uniform float u_bar_width_ratio;
uniform float u_min_height;
uniform float u_max_height;
uniform int u_mirror;
uniform vec3 u_colors[8];
uniform int u_color_count;
uniform int u_color_mode;
uniform int u_height_reference;    // 0=per_bar, 1=universal
uniform float u_intensity;
uniform vec2 u_offset;
uniform float u_scale;
uniform float u_rotation;
uniform float u_bar_roundness;
uniform int u_mirror_spectrum;
uniform int u_mirror_half;

uniform int u_shadow_enabled;
uniform vec3 u_shadow_color;
uniform float u_shadow_opacity;
uniform vec2 u_shadow_offset;
uniform float u_shadow_size;
uniform float u_shadow_blur;

in vec2 v_texcoord;
out vec4 fragColor;

vec3 get_bar_color(float t) {
    if (u_color_count <= 1) {
        return u_colors[0];
    }
    float idx_f = t * float(u_color_count - 1);
    int idx = int(floor(idx_f));
    float fract_t = idx_f - float(idx);
    idx = clamp(idx, 0, u_color_count - 2);
    return mix(u_colors[idx], u_colors[idx + 1], fract_t);
}

// Returns vec4(color, alpha) for a bar at the given uv.
// size_scale stretches bar dimensions (used for shadow sizing).
vec4 compute_bar(vec2 uv, float size_scale) {
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        return vec4(0.0);
    }

    float bar_width = 1.0 / float(u_bar_count);
    float gap = bar_width * (1.0 - u_bar_width_ratio);

    int bar_index = int(floor(uv.x / bar_width));
    bar_index = clamp(bar_index, 0, u_bar_count - 1);

    float bar_local_x = (uv.x - float(bar_index) * bar_width) / bar_width;

    // Check if we're in the gap
    if (bar_local_x < gap * 0.5 || bar_local_x > 1.0 - gap * 0.5) {
        return vec4(0.0);
    }

    int mag_idx = bar_index;
    if (u_mirror_spectrum == 1) {
        int half = u_bar_count / 2;
        int dist_from_center = abs(bar_index - half);
        if (u_mirror_half == 0) {
            mag_idx = dist_from_center;
        } else {
            mag_idx = half - 1 - dist_from_center;
        }
        mag_idx = clamp(mag_idx, 0, u_bar_count - 1);
    }
    float magnitude = u_magnitudes[mag_idx];
    float bar_height = mix(u_min_height, u_max_height, magnitude) * size_scale;

    // Rounding parameters
    float half_w = bar_width * u_bar_width_ratio * 0.5;
    float r = u_bar_roundness * half_w;
    float cx = (bar_local_x - 0.5) * bar_width;  // x offset from bar center

    float y = uv.y;
    if (u_mirror == 1) {
        y = abs(y - 0.5) * 2.0;
        if (y < bar_height) {
            // Round top (folded end)
            if (r > 0.0 && y > bar_height - r) {
                float dy = y - (bar_height - r);
                if (cx * cx + dy * dy > r * r) return vec4(0.0);
            }
            float color_t;
            if (u_color_mode == 1) {
                if (u_height_reference == 1) {
                    color_t = y / u_max_height;
                } else {
                    color_t = y / bar_height;
                }
            } else {
                color_t = float(bar_index) / float(u_bar_count);
            }
            vec3 color = get_bar_color(color_t);
            float base_intensity = 1.0 - (y / bar_height) * 0.3;
            return vec4(color * base_intensity * u_intensity, 1.0);
        }
        return vec4(0.0);
    } else {
        if (y < bar_height) {
            // Round top only
            if (r > 0.0 && y > bar_height - r) {
                float dy = y - (bar_height - r);
                if (cx * cx + dy * dy > r * r) return vec4(0.0);
            }
            float color_t;
            if (u_color_mode == 1) {
                if (u_height_reference == 1) {
                    color_t = y / u_max_height;
                } else {
                    color_t = y / bar_height;
                }
            } else {
                color_t = float(bar_index) / float(u_bar_count);
            }
            vec3 color = get_bar_color(color_t);
            float base_intensity = 0.7 + 0.3 * (y / bar_height);
            return vec4(color * base_intensity * u_intensity, 1.0);
        }
        return vec4(0.0);
    }
}

void main() {
    vec2 uv = v_texcoord;

    // Apply transform (offset in screen space, before scale)
    uv -= 0.5;
    uv -= u_offset;
    uv /= u_scale;
    float c = cos(u_rotation), s = sin(u_rotation);
    uv = mat2(c, s, -s, c) * uv;
    uv += 0.5;

    // Shadow pass
    if (u_shadow_enabled == 1) {
        vec2 shadow_uv = uv - u_shadow_offset;
        vec4 shadow_bar = compute_bar(shadow_uv, u_shadow_size);
        if (shadow_bar.a > 0.0) {
            // Compute soft edge via distance to bar boundary for blur
            float alpha = shadow_bar.a * u_shadow_opacity;
            // Simple blur: sample nearby and use smoothstep falloff
            if (u_shadow_blur > 0.0) {
                vec4 center = compute_bar(shadow_uv, u_shadow_size);
                // Check distance to edge by sampling offset points
                float edge_sum = 0.0;
                float samples = 0.0;
                for (float dx = -1.0; dx <= 1.0; dx += 1.0) {
                    for (float dy = -1.0; dy <= 1.0; dy += 1.0) {
                        vec2 s_uv = shadow_uv + vec2(dx, dy) * u_shadow_blur;
                        edge_sum += compute_bar(s_uv, u_shadow_size).a;
                        samples += 1.0;
                    }
                }
                alpha = (edge_sum / samples) * u_shadow_opacity;
            }
            // Store shadow; bar pass may overwrite
            fragColor = vec4(u_shadow_color * alpha, alpha);
        } else {
            fragColor = vec4(0.0);
        }
    } else {
        fragColor = vec4(0.0);
    }

    // Bar pass
    vec4 bar = compute_bar(uv, 1.0);
    if (bar.a > 0.0) {
        fragColor = bar;
    }
}
