#version 330 core

uniform sampler2D u_waveform_tex;
uniform int u_sample_count;
uniform float u_line_thickness;
uniform vec3 u_color;
uniform vec2 u_resolution;
uniform float u_amplitude;
uniform float u_time;
uniform int u_filled;
uniform float u_glow_intensity;
uniform float u_wave_range;
uniform vec2 u_position;
uniform float u_scale;
uniform float u_rotation;

in vec2 v_texcoord;
out vec4 fragColor;

float get_sample(float x) {
    return texture(u_waveform_tex, vec2(x, 0.5)).r;
}

void main() {
    vec2 uv = v_texcoord;

    // Inverse of rotate -> scale -> translate
    uv -= u_position;
    uv /= max(u_scale, 0.001);
    float c = cos(u_rotation), s = sin(u_rotation);
    uv = mat2(c, s, -s, c) * uv;
    uv += 0.5;

    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    // Sample waveform at current x via texture lookup (hardware-interpolated)
    float sample_val = get_sample(uv.x);

    // Map sample value to y position (centered at 0.5)
    float wave_y = 0.5 + sample_val * u_wave_range;

    // Pixel size for anti-aliased line thickness
    float pixel_y = 1.0 / u_resolution.y;
    float thickness = u_line_thickness * pixel_y * u_resolution.y * 0.01;

    float dist = abs(uv.y - wave_y);

    if (u_filled == 1) {
        // Filled mode: fill from center to waveform
        float center = 0.5;
        float top = max(center, wave_y);
        float bottom = min(center, wave_y);
        if (uv.y >= bottom && uv.y <= top) {
            float fill_intensity = 0.6 + 0.4 * (1.0 - dist / abs(wave_y - center + 0.001));
            fragColor = vec4(u_color * fill_intensity, 0.8);
        } else {
            fragColor = vec4(0.0);
        }
    } else {
        // Line mode
        if (dist < thickness) {
            float alpha = 1.0 - smoothstep(thickness * 0.5, thickness, dist);
            vec3 glow_color = u_color * (1.0 + u_amplitude * 0.5);
            fragColor = vec4(glow_color, alpha);
        } else {
            // Glow effect
            float glow = exp(-dist * dist * 500.0) * u_amplitude * u_glow_intensity;
            if (glow > 0.01) {
                fragColor = vec4(u_color * glow, glow);
            } else {
                fragColor = vec4(0.0);
            }
        }
    }
}
