#version 330 core

in vec2 v_texcoord;
out vec4 fragColor;

uniform sampler2D u_scene;
uniform vec2 u_resolution;
uniform float u_time;

// Vignette
uniform int u_vignette_enabled;
uniform float u_vignette_intensity;
uniform int u_vignette_shape;     // 0=circular, 1=rectangular, 2=diamond

// Chromatic aberration
uniform int u_chromatic_enabled;
uniform float u_chromatic_intensity;
uniform int u_chromatic_direction; // 0=radial, 1=linear
uniform float u_chromatic_angle;   // radians

// Glitch
uniform int u_glitch_enabled;
uniform float u_glitch_intensity;
uniform int u_glitch_type;        // 0=scanline, 1=block, 2=digital

// Film grain
uniform int u_grain_enabled;
uniform float u_grain_intensity;

// Bloom
uniform int u_bloom_enabled;
uniform float u_bloom_intensity;
uniform float u_bloom_threshold;

// Scanlines
uniform int u_scanline_enabled;
uniform float u_scanline_intensity;
uniform float u_scanline_density;

// Color shift
uniform int u_color_shift_enabled;
uniform float u_color_shift_intensity;

// --- Pseudo-random hash ---

float hash(float n) {
    return fract(sin(n) * 43758.5453123);
}

float hash2(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

// --- Glitch ---

vec4 apply_glitch_scanline(vec2 uv) {
    float time_seed = floor(u_time * 8.0);
    float line_height = 0.02 + 0.03 * hash(time_seed * 3.7);
    float band = floor(uv.y / line_height);
    float rand_val = hash(band * 13.37 + time_seed);

    // Only displace some bands (probability scales with intensity)
    if (rand_val < u_glitch_intensity * 0.6) {
        float offset = (hash(band * 7.13 + time_seed * 2.0) - 0.5) * u_glitch_intensity * 0.15;
        uv.x = fract(uv.x + offset);
    }
    return texture(u_scene, uv);
}

vec4 apply_glitch_block(vec2 uv) {
    float time_seed = floor(u_time * 6.0);
    vec4 color = texture(u_scene, uv);

    // Generate a few random blocks per frame
    for (int i = 0; i < 5; i++) {
        float fi = float(i);
        vec2 block_pos = vec2(hash(fi * 17.3 + time_seed), hash(fi * 31.7 + time_seed * 1.3));
        vec2 block_size = vec2(
            0.05 + 0.15 * hash(fi * 43.1 + time_seed),
            0.01 + 0.04 * hash(fi * 59.3 + time_seed)
        );

        if (uv.x > block_pos.x && uv.x < block_pos.x + block_size.x &&
            uv.y > block_pos.y && uv.y < block_pos.y + block_size.y) {
            float prob = hash(fi * 73.1 + time_seed);
            if (prob < u_glitch_intensity * 0.8) {
                vec2 displaced = uv + vec2(
                    (hash(fi * 97.1 + time_seed) - 0.5) * u_glitch_intensity * 0.2,
                    0.0
                );
                color = texture(u_scene, fract(displaced));
                // Optional color shift
                float shift = (hash(fi * 101.3 + time_seed) - 0.5) * u_glitch_intensity * 0.3;
                color.r = texture(u_scene, fract(displaced + vec2(shift, 0.0))).r;
            }
        }
    }
    return color;
}

vec4 apply_glitch_digital(vec2 uv) {
    float time_seed = floor(u_time * 8.0);
    float line_height = 0.02 + 0.03 * hash(time_seed * 3.7);
    float band = floor(uv.y / line_height);
    float rand_val = hash(band * 13.37 + time_seed);

    vec2 displaced_uv = uv;
    float rgb_split = 0.0;

    if (rand_val < u_glitch_intensity * 0.6) {
        float offset = (hash(band * 7.13 + time_seed * 2.0) - 0.5) * u_glitch_intensity * 0.15;
        displaced_uv.x = fract(uv.x + offset);
        rgb_split = u_glitch_intensity * 0.01 * hash(band * 11.0 + time_seed);
    }

    // RGB channel separation on displaced lines
    vec4 color;
    color.r = texture(u_scene, displaced_uv + vec2(rgb_split, 0.0)).r;
    color.g = texture(u_scene, displaced_uv).g;
    color.b = texture(u_scene, displaced_uv - vec2(rgb_split, 0.0)).b;
    color.a = texture(u_scene, displaced_uv).a;
    return color;
}

vec4 apply_glitch(vec2 uv) {
    if (u_glitch_type == 1) {
        return apply_glitch_block(uv);
    } else if (u_glitch_type == 2) {
        return apply_glitch_digital(uv);
    }
    return apply_glitch_scanline(uv);
}

// --- Chromatic Aberration ---

vec4 apply_chromatic(vec2 uv, vec4 center_color) {
    vec2 texel = 1.0 / u_resolution;
    float offset_px = u_chromatic_intensity * 20.0;
    vec2 offset_dir;

    if (u_chromatic_direction == 1) {
        // Linear: direction from angle
        offset_dir = vec2(cos(u_chromatic_angle), sin(u_chromatic_angle));
    } else {
        // Radial: direction from center to current pixel
        offset_dir = normalize(uv - 0.5);
    }

    vec2 offset = offset_dir * offset_px * texel;

    float r = texture(u_scene, uv + offset).r;
    float g = center_color.g;
    float b = texture(u_scene, uv - offset).b;
    return vec4(r, g, b, center_color.a);
}

// --- Film Grain ---

vec4 apply_grain(vec4 color) {
    vec2 noise_coord = gl_FragCoord.xy + vec2(u_time * 1000.0, u_time * 573.0);
    float noise = hash2(noise_coord) * 2.0 - 1.0;

    // Luminance-weighted: more visible in shadows/midtones
    float luma = dot(color.rgb, vec3(0.2126, 0.7152, 0.0722));
    noise *= (1.0 - 0.5 * luma);

    color.rgb += vec3(noise * u_grain_intensity * 0.3);
    color.rgb = clamp(color.rgb, 0.0, 1.0);
    return color;
}

// --- Vignette ---

vec4 apply_vignette(vec2 uv, vec4 color) {
    vec2 centered = uv - 0.5;
    float dist;

    if (u_vignette_shape == 1) {
        // Rectangular: Chebyshev distance
        dist = max(abs(centered.x), abs(centered.y)) * 2.0;
    } else if (u_vignette_shape == 2) {
        // Diamond: Manhattan distance
        dist = (abs(centered.x) + abs(centered.y)) * 1.5;
    } else {
        // Circular: Euclidean distance
        dist = length(centered) * 2.0;
    }

    // Map intensity to vignette reach: 0=no visible darkening, 1=heavy
    // At intensity 0: inner=2.0 (well past max dist ~1.41), outer=2.5 -> no darkening
    // At intensity 1: inner=0.2, outer=0.7 -> heavy vignette
    float inner = 2.0 - u_vignette_intensity * 1.8;
    float outer = inner + 0.5;
    float factor = smoothstep(outer, inner, dist);
    color.rgb *= factor;
    return color;
}

// --- Bloom ---

vec4 apply_bloom(vec2 uv, vec4 color) {
    vec2 texel = 1.0 / u_resolution;
    float radius = u_bloom_intensity * 10.0;
    float threshold = u_bloom_threshold;

    vec3 bloom = vec3(0.0);
    float total = 0.0;

    // 13-tap cross pattern (horizontal + vertical) for efficiency
    for (int i = -6; i <= 6; i++) {
        float fi = float(i);
        float w = exp(-(fi * fi) / max(radius * 0.5, 0.001));

        vec4 sh = texture(u_scene, uv + vec2(fi * texel.x * radius, 0.0));
        vec4 sv = texture(u_scene, uv + vec2(0.0, fi * texel.y * radius));

        float lh = dot(sh.rgb, vec3(0.2126, 0.7152, 0.0722));
        float lv = dot(sv.rgb, vec3(0.2126, 0.7152, 0.0722));

        bloom += sh.rgb * max(lh - threshold, 0.0) * w;
        bloom += sv.rgb * max(lv - threshold, 0.0) * w;
        total += w * 2.0;
    }

    bloom /= max(total, 0.001);
    color.rgb += bloom * u_bloom_intensity * 3.0;
    color.rgb = clamp(color.rgb, 0.0, 1.0);
    return color;
}

// --- Scanlines ---

vec4 apply_scanlines(vec2 uv, vec4 color) {
    // density 0 = 100 lines, 1 = 800 lines (denser)
    float line_count = mix(100.0, 800.0, u_scanline_density);
    float scanline = sin(uv.y * line_count * 3.14159) * 0.5 + 0.5;
    float strength = u_scanline_intensity * 0.6;
    color.rgb *= 1.0 - strength * (1.0 - scanline);
    return color;
}

// --- Color Shift (global hue rotation) ---

vec3 ge_rgb2hsv(vec3 c) {
    vec4 K = vec4(0.0, -1.0/3.0, 2.0/3.0, -1.0);
    vec4 p = mix(vec4(c.bg, K.wz), vec4(c.gb, K.xy), step(c.b, c.g));
    vec4 q = mix(vec4(p.xyw, c.r), vec4(c.r, p.yzx), step(p.x, c.r));
    float d = q.x - min(q.w, q.y);
    float e = 1.0e-10;
    return vec3(abs(q.z + (q.w - q.y) / (6.0 * d + e)), d / (q.x + e), q.x);
}

vec3 ge_hsv2rgb(vec3 c) {
    vec4 K = vec4(1.0, 2.0/3.0, 1.0/3.0, 3.0);
    vec3 p = abs(fract(c.xxx + K.xyz) * 6.0 - K.www);
    return c.z * mix(K.xxx, clamp(p - K.xxx, 0.0, 1.0), c.y);
}

vec4 apply_color_shift(vec4 color) {
    vec3 hsv = ge_rgb2hsv(color.rgb);
    hsv.x = fract(hsv.x + u_color_shift_intensity);
    return vec4(ge_hsv2rgb(hsv), color.a);
}

// --- Main ---

void main() {
    vec2 uv = v_texcoord;
    vec4 color;

    // 1. Glitch (displaces pixels, must sample texture)
    if (u_glitch_enabled == 1 && u_glitch_intensity > 0.001) {
        color = apply_glitch(uv);
    } else {
        color = texture(u_scene, uv);
    }

    // 2. Chromatic aberration (splits RGB channels)
    if (u_chromatic_enabled == 1 && u_chromatic_intensity > 0.001) {
        color = apply_chromatic(uv, color);
    }

    // 3. Bloom (bright area glow, samples neighbors)
    if (u_bloom_enabled == 1 && u_bloom_intensity > 0.001) {
        color = apply_bloom(uv, color);
    }

    // 4. Color shift (global hue rotation)
    if (u_color_shift_enabled == 1 && u_color_shift_intensity > 0.001) {
        color = apply_color_shift(color);
    }

    // 5. Scanlines (CRT overlay)
    if (u_scanline_enabled == 1 && u_scanline_intensity > 0.001) {
        color = apply_scanlines(uv, color);
    }

    // 6. Film grain (noise overlay)
    if (u_grain_enabled == 1 && u_grain_intensity > 0.001) {
        color = apply_grain(color);
    }

    // 7. Vignette (edge darkening, last)
    if (u_vignette_enabled == 1) {
        color = apply_vignette(uv, color);
    }

    fragColor = color;
}
