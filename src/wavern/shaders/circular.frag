#version 330 core

uniform float u_magnitudes[256];
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
uniform float u_bar_roundness;
uniform int u_mirror_spectrum;
uniform int u_mirror_half;
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

// Compute bar color at a given cartesian position (already centered and aspect-corrected).
// size_scale scales bar length for shadow sizing.
// Returns vec4(color, alpha). Does NOT render inner ring glow.
vec4 compute_bar(vec2 uv, float size_scale) {
    float scaled_inner = u_inner_radius * u_viz_scale * (1.0 + u_shape_bounce);
    float scaled_bar_length = u_bar_length * u_viz_scale * size_scale;

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
        return vec4(0.0);
    }

    int mag_idx = bar_idx;
    if (u_mirror_spectrum == 1) {
        int half = u_bar_count / 2;
        int dist_from_center = abs(bar_idx - half);
        if (u_mirror_half == 0) {
            mag_idx = dist_from_center;
        } else {
            mag_idx = half - 1 - dist_from_center;
        }
        mag_idx = clamp(mag_idx, 0, u_bar_count - 1);
    }
    float magnitude = u_magnitudes[mag_idx];
    float outer_radius = scaled_inner + magnitude * scaled_bar_length;

    if (dist >= scaled_inner && dist <= outer_radius) {
        // Bar roundness: round the outer tip
        float half_arc = bar_angular_width * 0.5 * scaled_inner;
        float r = u_bar_roundness * half_arc;
        if (r > 0.0 && dist > outer_radius - r) {
            float dy = dist - (outer_radius - r);
            float dx = angle_diff * dist;
            if (dx * dx + dy * dy > r * r) return vec4(0.0);
        }

        float t = (dist - scaled_inner) / (outer_radius - scaled_inner);
        float bar_pos = float(bar_idx) / float(u_bar_count);
        vec3 color = get_color(bar_pos);

        // Fade at edges
        float edge_fade = 1.0 - smoothstep(bar_angular_width * 0.3, bar_angular_width * 0.5, angle_diff);
        float intensity = (0.7 + 0.3 * t) * edge_fade;

        // Glow at tips
        float tip_glow = smoothstep(0.8, 1.0, t) * magnitude * u_glow_intensity;
        color += tip_glow;

        return vec4(color * intensity, 1.0);
    }

    return vec4(0.0);
}

void main() {
    // Center UV coordinates and correct aspect ratio
    vec2 uv = v_texcoord * 2.0 - 1.0;
    float aspect = u_resolution.x / u_resolution.y;
    uv.x *= aspect;

    // Apply center offset
    uv -= u_center_offset;

    float scaled_inner = u_inner_radius * u_viz_scale * (1.0 + u_shape_bounce);

    // Shadow pass
    if (u_shadow_enabled == 1) {
        vec2 shadow_uv = uv - u_shadow_offset;
        vec4 shadow_bar = compute_bar(shadow_uv, u_shadow_size);
        if (shadow_bar.a > 0.0) {
            float alpha = shadow_bar.a * u_shadow_opacity;
            if (u_shadow_blur > 0.0) {
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
    } else if (fragColor.a == 0.0) {
        float dist = length(uv);

        if (dist < scaled_inner) {
            // Image inside circle
            if (u_image_enabled == 1) {
                float base_r = scaled_inner * (1.0 - u_image_padding);
                float display_r = base_r * (1.0 + u_image_bounce);
                // Scale mode: UV uses base_r (image stretches to fill)
                // Zoom mode: UV uses display_r (image reveals more content)
                float uv_r = (u_image_bounce_zoom == 1) ? display_r : base_r;

                if (dist < display_r && display_r > 0.0) {
                    vec2 img_uv = uv / uv_r * 0.5 + 0.5;

                    // Cover mode: scale shorter axis to fill circle
                    vec2 tex_size = vec2(textureSize(u_image_tex, 0));
                    float img_aspect = tex_size.x / tex_size.y;
                    if (img_aspect > 1.0) {
                        img_uv.x = (img_uv.x - 0.5) / img_aspect + 0.5;
                    } else {
                        img_uv.y = (img_uv.y - 0.5) * img_aspect + 0.5;
                    }

                    if (img_uv.x >= 0.0 && img_uv.x <= 1.0 &&
                        img_uv.y >= 0.0 && img_uv.y <= 1.0) {
                        vec4 img_color = texture(u_image_tex, img_uv);
                        float edge = smoothstep(display_r, display_r - 0.003, dist);
                        fragColor = vec4(img_color.rgb, img_color.a * edge);
                    }
                }
            }

            // Inner ring glow (on top of image at border)
            if (dist > scaled_inner - 0.005) {
                float angle = atan(uv.y, uv.x) + PI;
                float ring_glow = u_amplitude * u_glow_intensity * 0.6;
                vec3 glow_color = get_color(angle / (2.0 * PI));
                fragColor.rgb += glow_color * ring_glow;
                fragColor.a = max(fragColor.a, ring_glow);
            }
        }
    }
}
