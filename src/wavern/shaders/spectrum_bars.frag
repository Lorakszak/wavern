#version 330 core

uniform float u_magnitudes[128];
uniform int u_bar_count;
uniform float u_bar_width_ratio;
uniform float u_min_height;
uniform float u_max_height;
uniform int u_mirror;
uniform vec3 u_colors[8];
uniform int u_color_count;
uniform int u_color_mode;
uniform float u_intensity;
uniform vec2 u_offset;
uniform float u_scale;
uniform float u_rotation;

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

void main() {
    vec2 uv = v_texcoord;

    // Apply transform (offset in screen space, before scale)
    uv -= 0.5;
    uv -= u_offset;
    uv /= u_scale;
    float c = cos(u_rotation), s = sin(u_rotation);
    uv = mat2(c, s, -s, c) * uv;
    uv += 0.5;

    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    float bar_width = 1.0 / float(u_bar_count);
    float gap = bar_width * (1.0 - u_bar_width_ratio);

    int bar_index = int(floor(uv.x / bar_width));
    bar_index = clamp(bar_index, 0, u_bar_count - 1);

    float bar_local_x = (uv.x - float(bar_index) * bar_width) / bar_width;

    // Check if we're in the gap
    if (bar_local_x < gap * 0.5 || bar_local_x > 1.0 - gap * 0.5) {
        fragColor = vec4(0.0, 0.0, 0.0, 0.0);
        return;
    }

    float magnitude = u_magnitudes[bar_index];
    float bar_height = mix(u_min_height, u_max_height, magnitude);

    float y = uv.y;
    if (u_mirror == 1) {
        y = abs(y - 0.5) * 2.0;
        if (y < bar_height) {
            float color_t;
            if (u_color_mode == 1) {
                color_t = y / bar_height;
            } else {
                color_t = float(bar_index) / float(u_bar_count);
            }
            vec3 color = get_bar_color(color_t);
            float base_intensity = 1.0 - (y / bar_height) * 0.3;
            fragColor = vec4(color * base_intensity * u_intensity, 1.0);
        } else {
            fragColor = vec4(0.0, 0.0, 0.0, 0.0);
        }
    } else {
        if (y < bar_height) {
            float color_t;
            if (u_color_mode == 1) {
                color_t = y / bar_height;
            } else {
                color_t = float(bar_index) / float(u_bar_count);
            }
            vec3 color = get_bar_color(color_t);
            float base_intensity = 0.7 + 0.3 * (y / bar_height);
            fragColor = vec4(color * base_intensity * u_intensity, 1.0);
        } else {
            fragColor = vec4(0.0, 0.0, 0.0, 0.0);
        }
    }
}
