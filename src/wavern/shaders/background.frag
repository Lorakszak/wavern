#version 330 core

in vec2 v_texcoord;
out vec4 fragColor;

uniform sampler2D u_background;

// Transform uniforms
uniform float u_rotation;       // rotation in radians
uniform int u_mirror_x;         // 1 = mirror horizontally
uniform int u_mirror_y;         // 1 = mirror vertically

// Movement uniforms
uniform float u_time;
uniform int u_movement_type;    // 0=none, 1=drift, 2=shake, 3=wave, 4=zoom_pulse, 5=breathe
uniform float u_movement_speed;
uniform float u_movement_intensity;
uniform float u_movement_angle;
uniform int u_clamp_to_frame;   // 1 = prevent out-of-bounds UVs

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

vec2 apply_movement(vec2 uv, float time) {
    float intensity = u_movement_intensity;

    // Pre-zoom inward to compensate for effect displacement when clamping
    if (u_clamp_to_frame == 1 && u_movement_type != 0) {
        float padding = 0.0;
        if (u_movement_type == 2) {
            // shake: max offset = intensity * 0.02
            padding = intensity * 0.02;
        } else if (u_movement_type == 3) {
            // wave: max offset = intensity * 0.03
            padding = intensity * 0.03;
        } else if (u_movement_type == 4) {
            // zoom_pulse: max zoom-out = intensity * 0.05
            padding = intensity * 0.05;
        } else if (u_movement_type == 5) {
            // breathe: max zoom-out = intensity * 0.03
            padding = intensity * 0.03;
        }
        if (padding > 0.0) {
            // Translation effects (shake, wave) need additive margin;
            // multiplicative effects (zoom_pulse, breathe) cancel their own scale.
            float scale = (u_movement_type == 2 || u_movement_type == 3)
                ? 1.0 - 2.0 * padding
                : 1.0 / (1.0 + padding);
            uv = 0.5 + (uv - 0.5) * scale;
        }
    }

    if (u_movement_type == 1) {
        // drift — continuous directional scroll
        float angle = u_movement_angle;
        uv += time * u_movement_speed * vec2(cos(angle), sin(angle)) * intensity * 0.1;
    } else if (u_movement_type == 2) {
        // shake — pseudo-random per-frame jitter
        float t = floor(time * u_movement_speed * 8.0);
        uv += intensity * 0.02 * vec2(hash(t), hash(t + 100.0)) * 2.0 - intensity * 0.02;
    } else if (u_movement_type == 3) {
        // wave — sinusoidal distortion
        uv.x += sin(uv.y * 10.0 + time * u_movement_speed) * intensity * 0.03;
        uv.y += cos(uv.x * 10.0 + time * u_movement_speed * 0.7) * intensity * 0.03;
    } else if (u_movement_type == 4) {
        // zoom_pulse — rhythmic zoom in/out
        float s = 1.0 + sin(time * u_movement_speed) * intensity * 0.05;
        uv = 0.5 + (uv - 0.5) * s;
    } else if (u_movement_type == 5) {
        // breathe — gentle slow zoom oscillation
        float s = 1.0 + sin(time * u_movement_speed * 0.3) * intensity * 0.03;
        uv = 0.5 + (uv - 0.5) * s;
    }

    // Clamp UV to prevent out-of-bounds sampling
    if (u_clamp_to_frame == 1) {
        uv = clamp(uv, vec2(0.0), vec2(1.0));
    }

    return uv;
}

void main() {
    vec2 uv = v_texcoord;
    uv = apply_rotation(uv, u_rotation);
    uv = apply_mirror(uv);
    uv = apply_movement(uv, u_time);
    fragColor = texture(u_background, uv);
}
