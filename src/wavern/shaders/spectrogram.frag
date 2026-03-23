#version 330 core

// Ring-buffer history texture: width=history_length, height=n_bins (single channel float)
uniform sampler2D u_history_tex;
uniform int u_history_length;
uniform int u_n_bins;
// write_pos is the most-recently written column (newest data)
uniform int u_write_pos;

uniform int u_scroll_dir;    // 0=left, 1=right, 2=up, 3=down
uniform int u_color_map;     // 0=palette, 1=inferno, 2=magma, 3=viridis, 4=plasma, 5=grayscale
uniform float u_brightness;
uniform float u_contrast;
uniform float u_saturation;
uniform float u_blur;
uniform int u_bar_separation;

uniform vec3 u_colors[8];
uniform int u_color_count;

uniform vec2 u_resolution;
uniform vec2 u_offset;
uniform float u_viz_scale;

in vec2 v_texcoord;
out vec4 fragColor;

// ---------------------------------------------------------------------------
// Color maps (polynomial fits by Matt Zucker / Sam Skillman, CC0 licensed)
// ---------------------------------------------------------------------------

vec3 inferno(float t) {
    const vec3 c0 = vec3(0.0002189403691192265, 0.001651004631001012, -0.01948089843709184);
    const vec3 c1 = vec3(0.1065134194856116, 0.5639564367884091, 3.932712388889277);
    const vec3 c2 = vec3(11.60249308247187, -3.972853965665698, -15.9423941062914);
    const vec3 c3 = vec3(-41.70399613139459, 17.43639888205313, 44.35414519872813);
    const vec3 c4 = vec3(77.162935699427, -33.40235894210092, -81.80730925738993);
    const vec3 c5 = vec3(-71.31942824499214, 32.62606426397723, 73.20951985803202);
    const vec3 c6 = vec3(25.13112622477341, -12.24266895238567, -23.07032500287172);
    return clamp(c0 + t*(c1 + t*(c2 + t*(c3 + t*(c4 + t*(c5 + t*c6))))), 0.0, 1.0);
}

vec3 magma(float t) {
    const vec3 c0 = vec3(-0.002136485053939582, -0.000749655052795221, -0.005386127855323933);
    const vec3 c1 = vec3(0.2516605407371642, 0.6775232436837668, 2.494026599312351);
    const vec3 c2 = vec3(8.353717279216625, -3.577719514958484, 0.3144679030132573);
    const vec3 c3 = vec3(-27.66873308576866, 14.26473078096533, -13.64921318813922);
    const vec3 c4 = vec3(52.17613981234133, -27.94360607168351, 12.94416944238394);
    const vec3 c5 = vec3(-50.76852536473588, 29.04658282127291, 4.23415299384598);
    const vec3 c6 = vec3(18.65570506591883, -11.48977351997711, -5.601961508734096);
    return clamp(c0 + t*(c1 + t*(c2 + t*(c3 + t*(c4 + t*(c5 + t*c6))))), 0.0, 1.0);
}

vec3 viridis(float t) {
    const vec3 c0 = vec3(0.2777273272234177, 0.005407344544966578, 0.3340998053353061);
    const vec3 c1 = vec3(0.1050930431085774, 1.404613529898575, 1.384590162594685);
    const vec3 c2 = vec3(-0.3308618287255563, 0.214847559468213, 0.09509516302823659);
    const vec3 c3 = vec3(-4.634230498983486, -5.799100973351585, -19.33244095627987);
    const vec3 c4 = vec3(6.228269936347081, 14.17993336680509, 56.69055260068105);
    const vec3 c5 = vec3(4.776384997670288, -13.74514537774601, -65.35303263337234);
    const vec3 c6 = vec3(-0.5151774132690155, 4.645852612178535, 26.3124352495832);
    return clamp(c0 + t*(c1 + t*(c2 + t*(c3 + t*(c4 + t*(c5 + t*c6))))), 0.0, 1.0);
}

vec3 plasma(float t) {
    const vec3 c0 = vec3(0.05873234392399702, 0.02333670892565664, 0.5433401826748754);
    const vec3 c1 = vec3(2.176514634195958, 0.2383834171260182, 0.7539604599784036);
    const vec3 c2 = vec3(-2.689460476458034, -7.455851135738909, 3.110799939717086);
    const vec3 c3 = vec3(6.130348345893603, 42.3461881477227, -28.51885465631967);
    const vec3 c4 = vec3(-11.10743619062271, -82.66631109428045, 60.13984767418263);
    const vec3 c5 = vec3(10.02306557647065, 71.41361770095349, -54.07218655560067);
    const vec3 c6 = vec3(-3.658713842777788, -22.93153465461149, 18.19190778539828);
    return clamp(c0 + t*(c1 + t*(c2 + t*(c3 + t*(c4 + t*(c5 + t*c6))))), 0.0, 1.0);
}

vec3 palette_color(float t) {
    if (u_color_count <= 1) return u_colors[0];
    float idx_f = t * float(u_color_count - 1);
    int idx = clamp(int(floor(idx_f)), 0, u_color_count - 2);
    return mix(u_colors[idx], u_colors[idx + 1], idx_f - float(idx));
}

// Adjust saturation: 0=greyscale, 1=unchanged, 2=doubled
vec3 adjust_saturation(vec3 color, float sat) {
    float lum = dot(color, vec3(0.2126, 0.7152, 0.0722));
    return clamp(mix(vec3(lum), color, sat), 0.0, 1.0);
}

// ---------------------------------------------------------------------------
// Ring-buffer aware texture lookup
// ---------------------------------------------------------------------------

// tex_uv.x = time axis (ring buffer, wraps), tex_uv.y = freq axis (clamped)
// ring_newest  = float(write_pos) / float(history_length)  — most recently written
// ring_oldest  = ring_newest + 1/history_length             — least recently written
float sample_history(float sx, float sy, float ring_newest, float ring_oldest) {
    vec2 tex_uv;
    if (u_scroll_dir == 0) {
        // left: oldest at screen left, newest at screen right; freq on y
        tex_uv = vec2(fract(sx + ring_oldest), sy);
    } else if (u_scroll_dir == 1) {
        // right: newest at screen left, oldest at screen right; freq on y
        tex_uv = vec2(fract(ring_newest - sx), sy);
    } else if (u_scroll_dir == 2) {
        // up: oldest at screen bottom, newest at screen top; freq on x
        tex_uv = vec2(fract(sy + ring_oldest), sx);
    } else {
        // down: newest at screen bottom, oldest at screen top; freq on x
        tex_uv = vec2(fract(ring_newest - sy), sx);
    }
    // Clamp frequency axis (always tex_uv.y) to prevent edge wrap
    tex_uv.y = clamp(tex_uv.y, 0.0, 1.0);
    return texture(u_history_tex, tex_uv).r;
}

void main() {
    // Viewport transform (offset + scale around center)
    vec2 uv = (v_texcoord - 0.5) / u_viz_scale + 0.5 - u_offset;
    if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
        fragColor = vec4(0.0);
        return;
    }

    float safe_history = max(float(u_history_length), 1.0);
    float ring_newest = float(u_write_pos) / safe_history;
    float ring_oldest = fract(ring_newest + 1.0 / safe_history);

    // Sample with optional blur (5x5 Gaussian in screen space)
    float value;
    if (u_blur > 0.001) {
        float px = 1.0 / u_resolution.x;
        float py = 1.0 / u_resolution.y;
        float sigma2 = max(u_blur * u_blur, 0.01);
        float total = 0.0, weight = 0.0;
        for (int dx = -2; dx <= 2; dx++) {
            for (int dy = -2; dy <= 2; dy++) {
                float dist2 = float(dx * dx + dy * dy);
                float w = exp(-dist2 / (2.0 * sigma2));
                total += sample_history(
                    uv.x + float(dx) * px,
                    uv.y + float(dy) * py,
                    ring_newest, ring_oldest
                ) * w;
                weight += w;
            }
        }
        value = total / weight;
    } else {
        value = sample_history(uv.x, uv.y, ring_newest, ring_oldest);
    }

    // Brightness and contrast
    value = clamp(value * u_brightness, 0.0, 1.0);
    value = clamp((value - 0.5) * u_contrast + 0.5, 0.0, 1.0);

    // Bar separation: darken at bin boundaries along frequency axis
    if (u_bar_separation == 1) {
        float freq_screen = (u_scroll_dir <= 1) ? uv.y : uv.x;
        float frac = fract(freq_screen * float(u_n_bins));
        if (frac < 0.06 || frac > 0.94) value *= 0.25;
    }

    // Colormap
    vec3 color;
    if (u_color_map == 1)      color = inferno(value);
    else if (u_color_map == 2) color = magma(value);
    else if (u_color_map == 3) color = viridis(value);
    else if (u_color_map == 4) color = plasma(value);
    else if (u_color_map == 5) color = vec3(value);
    else                       color = palette_color(value);

    // Saturation
    color = adjust_saturation(color, u_saturation);

    float alpha = (value < 0.001) ? 0.0 : 1.0;
    fragColor = vec4(color, alpha);
}
