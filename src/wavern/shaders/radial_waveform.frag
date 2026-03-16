#version 330 core

uniform sampler2D u_waveform_tex;
uniform int u_sample_count;
uniform float u_inner_radius;
uniform float u_wave_amplitude;
uniform float u_line_thickness;
uniform int u_filled;
uniform vec2 u_resolution;
uniform float u_time;
uniform float u_rotation_speed;
uniform float u_amplitude;
uniform float u_glow_intensity;
uniform float u_rotation_offset;
uniform vec2 u_center_offset;
uniform float u_viz_scale;
uniform int u_mirror_mode;  // 0=none, 1=mirror, 2=duplicate

uniform vec3 u_colors[8];
uniform int u_color_count;

uniform sampler2D u_image_tex;
uniform int u_image_enabled;
uniform float u_image_padding;
uniform float u_image_bounce;
uniform int u_image_bounce_zoom;
uniform float u_shape_bounce;
uniform float u_image_rotation;

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

// Sample waveform at normalized position t [0..1]
float get_waveform(float t) {
    return texture(u_waveform_tex, vec2(t, 0.5)).r;
}

void main() {
    vec2 uv = v_texcoord * 2.0 - 1.0;
    float aspect = u_resolution.x / u_resolution.y;
    uv.x *= aspect;

    // Apply center offset
    uv -= u_center_offset;

    float dist = length(uv);
    float angle = atan(uv.y, uv.x) + PI;  // [0, 2PI]

    // Apply rotation
    angle = mod(angle + u_time * u_rotation_speed + u_rotation_offset, 2.0 * PI);

    float scaled_inner = u_inner_radius * u_viz_scale * (1.0 + u_shape_bounce);
    float scaled_amplitude = u_wave_amplitude * u_viz_scale;

    // Map angle to waveform sample position [0, 1]
    float sample_t = angle / (2.0 * PI);

    // Handle mirror modes
    if (u_mirror_mode == 1) {
        // Mirror: fold second half onto first
        sample_t = 1.0 - abs(sample_t * 2.0 - 1.0);
    } else if (u_mirror_mode == 2) {
        // Duplicate: first half mapped to full range
        sample_t = mod(sample_t * 2.0, 1.0);
    }

    float wave_val = get_waveform(sample_t);
    float wave_radius = scaled_inner + wave_val * scaled_amplitude;

    // Pixel size in UV space for thickness calculation
    float pixel_size = 2.0 / u_resolution.y;
    float thickness = u_line_thickness * pixel_size;

    float color_t = sample_t;
    vec3 color = get_color(color_t);

    fragColor = vec4(0.0);

    if (u_filled == 1) {
        // Filled mode: fill between inner radius and waveform
        float min_r = min(scaled_inner, wave_radius);
        float max_r = max(scaled_inner, wave_radius);

        if (dist >= min_r && dist <= max_r) {
            float fill_t = (dist - min_r) / max(max_r - min_r, 0.001);
            float edge_fade = smoothstep(0.0, thickness * 2.0, dist - min_r)
                            * smoothstep(0.0, thickness * 2.0, max_r - dist);
            float intensity = 0.6 + 0.4 * (1.0 - fill_t);
            fragColor = vec4(color * intensity * edge_fade, edge_fade);
        }

        // Line at the waveform edge
        float edge_dist = abs(dist - wave_radius);
        if (edge_dist < thickness) {
            float line_alpha = smoothstep(thickness, 0.0, edge_dist);
            vec3 line_color = color * (0.8 + 0.2 * abs(wave_val));
            fragColor = mix(fragColor, vec4(line_color, 1.0), line_alpha);
        }
    } else {
        // Line mode: draw waveform as a line around the circle
        float edge_dist = abs(dist - wave_radius);
        if (edge_dist < thickness * 2.0) {
            float line_alpha = smoothstep(thickness, 0.0, edge_dist);
            float intensity = 0.8 + 0.2 * abs(wave_val);
            fragColor = vec4(color * intensity, line_alpha);
        }
    }

    // Glow effect around waveform line
    if (u_glow_intensity > 0.0) {
        float glow_dist = abs(dist - wave_radius);
        float glow_width = thickness * 8.0;
        float glow = exp(-glow_dist * glow_dist / (glow_width * glow_width))
                   * u_glow_intensity * (0.3 + 0.7 * abs(wave_val));
        vec3 glow_color = color * glow;
        fragColor.rgb += glow_color;
        fragColor.a = max(fragColor.a, glow * 0.5);
    }

    // Inner circle ring glow
    if (dist < scaled_inner && dist > scaled_inner - 0.005) {
        float ring_glow = u_amplitude * u_glow_intensity * 0.4;
        vec3 glow_color = get_color(angle / (2.0 * PI));
        fragColor.rgb += glow_color * ring_glow;
        fragColor.a = max(fragColor.a, ring_glow);
    }

    // Image inside circle
    if (dist < scaled_inner && u_image_enabled == 1) {
        float base_r = scaled_inner * (1.0 - u_image_padding);
        float display_r = base_r * (1.0 + u_image_bounce);
        float uv_r = (u_image_bounce_zoom == 1) ? display_r : base_r;

        if (dist < display_r && display_r > 0.0) {
            vec2 img_uv = uv / uv_r * 0.5 + 0.5;

            // Rotate image UVs
            float img_c = cos(u_image_rotation);
            float img_s = sin(u_image_rotation);
            img_uv -= 0.5;
            img_uv = vec2(img_uv.x * img_c - img_uv.y * img_s,
                          img_uv.x * img_s + img_uv.y * img_c);
            img_uv += 0.5;

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
                // Blend image behind waveform
                vec4 img_final = vec4(img_color.rgb, img_color.a * edge);
                fragColor = vec4(
                    mix(img_final.rgb, fragColor.rgb, fragColor.a),
                    max(fragColor.a, img_final.a)
                );
            }
        }
    }
}
