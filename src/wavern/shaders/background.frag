#version 330 core

in vec2 v_texcoord;
out vec4 fragColor;

uniform sampler2D u_background;

// Transform uniforms
uniform float u_rotation;
uniform int u_mirror_x;
uniform int u_mirror_y;

// Time
uniform float u_time;

// Per-movement uniforms
uniform int u_drift_enabled;
uniform float u_drift_speed;
uniform float u_drift_intensity;
uniform float u_drift_angle;
uniform int u_drift_clamp;

uniform int u_shake_enabled;
uniform float u_shake_speed;
uniform float u_shake_intensity;
uniform int u_shake_clamp;

uniform int u_wave_enabled;
uniform float u_wave_speed;
uniform float u_wave_intensity;
uniform int u_wave_clamp;

uniform int u_zoom_pulse_enabled;
uniform float u_zoom_pulse_speed;
uniform float u_zoom_pulse_intensity;
uniform int u_zoom_pulse_clamp;

uniform int u_breathe_enabled;
uniform float u_breathe_speed;
uniform float u_breathe_intensity;
uniform int u_breathe_clamp;

float hash(float x) {
    return fract(sin(x * 127.1) * 43758.5453);
}

vec2 apply_rotation(vec2 uv, float angle) {
    if (angle == 0.0) return uv;
    vec2 center = vec2(0.5);
    uv -= center;
    float c = cos(angle);
    float s = sin(angle);
    uv = vec2(uv.x * c - uv.y * s, uv.x * s + uv.y * c);
    uv += center;
    return uv;
}

vec2 apply_mirror(vec2 uv) {
    if (u_mirror_x == 1) uv.x = 1.0 - uv.x;
    if (u_mirror_y == 1) uv.y = 1.0 - uv.y;
    return uv;
}

vec2 apply_movements(vec2 uv, float time) {
    // Accumulate translation offsets and zoom scale factors additively
    vec2 offset = vec2(0.0);
    float scale = 1.0;

    // Accumulate clamp-to-frame padding
    float translate_padding = 0.0;
    float zoom_padding = 0.0;
    bool any_clamp = false;

    // --- Drift ---
    if (u_drift_enabled == 1) {
        float angle = u_drift_angle;
        offset += time * u_drift_speed * vec2(cos(angle), sin(angle)) * u_drift_intensity * 0.1;
        // Drift uses texture repeat, no clamp padding needed
    }

    // --- Shake ---
    if (u_shake_enabled == 1) {
        float t = floor(time * u_shake_speed * 8.0);
        offset += u_shake_intensity * 0.02 * vec2(hash(t), hash(t + 100.0)) * 2.0
                  - u_shake_intensity * 0.02;
        if (u_shake_clamp == 1) {
            translate_padding += u_shake_intensity * 0.02;
            any_clamp = true;
        }
    }

    // --- Wave ---
    if (u_wave_enabled == 1) {
        offset.x += sin(uv.y * 10.0 + time * u_wave_speed) * u_wave_intensity * 0.03;
        offset.y += cos(uv.x * 10.0 + time * u_wave_speed * 0.7) * u_wave_intensity * 0.03;
        if (u_wave_clamp == 1) {
            translate_padding += u_wave_intensity * 0.03;
            any_clamp = true;
        }
    }

    // --- Zoom Pulse ---
    if (u_zoom_pulse_enabled == 1) {
        float s = 1.0 + sin(time * u_zoom_pulse_speed) * u_zoom_pulse_intensity * 0.05;
        scale *= s;
        if (u_zoom_pulse_clamp == 1) {
            zoom_padding += u_zoom_pulse_intensity * 0.05;
            any_clamp = true;
        }
    }

    // --- Breathe ---
    if (u_breathe_enabled == 1) {
        float s = 1.0 + sin(time * u_breathe_speed * 0.3) * u_breathe_intensity * 0.03;
        scale *= s;
        if (u_breathe_clamp == 1) {
            zoom_padding += u_breathe_intensity * 0.03;
            any_clamp = true;
        }
    }

    // Apply clamp-to-frame compensation zoom
    if (any_clamp) {
        float clamp_scale = 1.0;
        if (translate_padding > 0.0) {
            clamp_scale *= (1.0 - 2.0 * translate_padding);
        }
        if (zoom_padding > 0.0) {
            clamp_scale *= 1.0 / (1.0 + zoom_padding);
        }
        uv = 0.5 + (uv - 0.5) * clamp_scale;
    }

    // Apply zoom around center
    uv = 0.5 + (uv - 0.5) * scale;

    // Apply translation
    uv += offset;

    // Clamp if any movement requests it
    if (any_clamp) {
        uv = clamp(uv, vec2(0.0), vec2(1.0));
    }

    return uv;
}

void main() {
    vec2 uv = v_texcoord;
    uv = apply_rotation(uv, u_rotation);
    uv = apply_mirror(uv);
    uv = apply_movements(uv, u_time);
    fragColor = texture(u_background, uv);
}
