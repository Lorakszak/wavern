#version 330 core

in vec2 v_texcoord;
out vec4 fragColor;

uniform sampler2D u_background;
uniform vec2 u_resolution;

// Per-effect enable flags
uniform int u_blur_enabled;
uniform int u_hue_shift_enabled;
uniform int u_saturation_enabled;
uniform int u_brightness_enabled;
uniform int u_pixelate_enabled;
uniform int u_posterize_enabled;
uniform int u_invert_enabled;

// Per-effect intensities (already audio-modulated by renderer)
uniform float u_blur_intensity;
uniform float u_hue_shift_intensity;
uniform float u_saturation_intensity;
uniform float u_brightness_intensity;
uniform float u_pixelate_intensity;
uniform float u_posterize_intensity;
uniform float u_invert_intensity;

// --- Blur: 13-tap Gaussian approximation ---

vec4 apply_blur(vec2 uv) {
    vec2 texel = 1.0 / u_resolution;
    float radius = u_blur_intensity * 20.0;

    // Gaussian weights for 13-tap kernel (sigma ~= radius/3)
    float weights[7] = float[7](
        0.1964825501511404,
        0.2969069646728344,
        0.2195956851498348,
        0.0855079709307994,
        0.0176032663382210,
        0.0019124423369498,
        0.0000109890209163
    );

    vec4 color = texture(u_background, uv) * weights[0];

    // Horizontal + vertical samples
    for (int i = 1; i < 7; i++) {
        float offset = float(i) * radius * texel.x;
        color += texture(u_background, uv + vec2(offset, 0.0)) * weights[i];
        color += texture(u_background, uv - vec2(offset, 0.0)) * weights[i];
    }
    for (int i = 1; i < 7; i++) {
        float offset = float(i) * radius * texel.y;
        color += texture(u_background, uv + vec2(0.0, offset)) * weights[i];
        color += texture(u_background, uv - vec2(0.0, offset)) * weights[i];
    }

    // Normalize: center weight + 2 * sum(side weights) for each axis
    // Total = weights[0] + 2*(sum(weights[1..6])) for horiz
    //       + 2*(sum(weights[1..6])) for vert
    // But we sampled both axes into one accumulator, so normalize accordingly.
    float side_sum = weights[1] + weights[2] + weights[3]
                   + weights[4] + weights[5] + weights[6];
    float total = weights[0] + 4.0 * side_sum;
    return color / total;
}

// --- Hue shift: RGB <-> HSV ---

vec3 rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0/3.0, 2.0/3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

vec3 hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0/3.0, 1.0/3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

vec4 apply_hue_shift(vec4 color) {
    vec3 hsv = rgb2hsv(color.rgb);
    hsv.x = fract(hsv.x + u_hue_shift_intensity);
    return vec4(hsv2rgb(hsv), color.a);
}

// --- Saturation ---

vec4 apply_saturation(vec4 color) {
    float luma = dot(color.rgb, vec3(0.2126, 0.7152, 0.0722));
    // intensity 0.0 = grayscale, 0.5 = normal, 1.0 = 2x saturated
    float factor = u_saturation_intensity * 2.0;
    vec3 result = mix(vec3(luma), color.rgb, factor);
    return vec4(clamp(result, 0.0, 1.0), color.a);
}

// --- Brightness ---

vec4 apply_brightness(vec4 color) {
    // intensity 0.0 = 0.5x, 0.5 = 1.0x (normal), 1.0 = 1.5x
    float factor = 0.5 + u_brightness_intensity;
    return vec4(clamp(color.rgb * factor, 0.0, 1.0), color.a);
}

// --- Pixelate ---

vec4 apply_pixelate(vec2 uv) {
    // intensity 0 = 1px blocks (no effect), 1 = 100px blocks (very chunky)
    float pixel_size = max(u_pixelate_intensity * 100.0, 1.0);
    vec2 grid = floor(uv * u_resolution / pixel_size) * pixel_size / u_resolution;
    return texture(u_background, grid);
}

// --- Posterize ---

vec4 apply_posterize(vec4 color) {
    // intensity 0 = 32 levels (subtle), 1 = 2 levels (extreme)
    float levels = mix(32.0, 2.0, u_posterize_intensity);
    vec3 posterized = floor(color.rgb * levels + 0.5) / levels;
    return vec4(clamp(posterized, 0.0, 1.0), color.a);
}

// --- Invert ---

vec4 apply_invert(vec4 color) {
    // intensity blends between original and inverted
    vec3 inverted = 1.0 - color.rgb;
    return vec4(mix(color.rgb, inverted, u_invert_intensity), color.a);
}

// --- Main ---

void main() {
    vec2 uv = v_texcoord;
    vec4 color;

    // 1. Pixelate (snaps UVs to grid, must run before other texture samples)
    if (u_pixelate_enabled == 1 && u_pixelate_intensity > 0.001) {
        color = apply_pixelate(uv);
    // 2. Blur (samples neighboring texels)
    } else if (u_blur_enabled == 1 && u_blur_intensity > 0.001) {
        color = apply_blur(uv);
    } else {
        color = texture(u_background, uv);
    }

    // 3. Hue shift
    if (u_hue_shift_enabled == 1 && u_hue_shift_intensity > 0.001) {
        color = apply_hue_shift(color);
    }

    // 4. Saturation
    if (u_saturation_enabled == 1) {
        color = apply_saturation(color);
    }

    // 5. Brightness
    if (u_brightness_enabled == 1) {
        color = apply_brightness(color);
    }

    // 6. Posterize (quantizes color levels)
    if (u_posterize_enabled == 1 && u_posterize_intensity > 0.001) {
        color = apply_posterize(color);
    }

    // 7. Invert (blends toward inverted colors)
    if (u_invert_enabled == 1 && u_invert_intensity > 0.001) {
        color = apply_invert(color);
    }

    fragColor = color;
}
