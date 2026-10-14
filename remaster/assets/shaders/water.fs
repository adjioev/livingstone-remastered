#version 330
// Water over the room background: the background itself is re-sampled with a ripple
// offset inside water cells, plus surface glints, soft caustics and falling streaks
// in waterfalls. Drawn as the full background quad; alpha is the water mask.
in vec2 fragTexCoord;
out vec4 finalColor;

uniform sampler2D texture0;   // room background
uniform sampler2D waterMask;  // R water, G surface (top of water), B waterfall; blurred
uniform float time;
uniform vec2 cellSize;        // one tile in uv

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}

void main() {
    vec2 uv = fragTexCoord;
    vec4 m = texture(waterMask, uv);
    float water = m.r, surface = m.g, fall = m.b;
    if (water < 0.01) { finalColor = vec4(0.0); return; }

    // ripple: horizontal wobble in pools, downward drift in falls
    float wob = sin(uv.y * 260.0 + time * 2.2) * 0.5 + sin(uv.y * 120.0 - time * 1.3 + uv.x * 40.0) * 0.5;
    vec2 off = vec2(wob * cellSize.x * 0.05 * (1.0 - fall), 0.0);
    vec3 col = texture(texture0, uv + off).rgb;

    // caustics: soft moving light network below the surface
    float c = vnoise(vec2(uv.x * 90.0 + time * 0.6, uv.y * 160.0 - time * 0.4));
    c = smoothstep(0.62, 0.95, c) * (1.0 - fall);
    col += c * 0.10;

    // surface glints: short bright dashes drifting along the top of the water
    float g = vnoise(vec2(uv.x * 140.0 - time * 1.5, uv.y * 30.0 + time * 0.3));
    col += smoothstep(0.72, 0.9, g) * surface * 0.45;

    // waterfall: bright streaks sliding down
    float s = vnoise(vec2(uv.x * 220.0, uv.y * 25.0 - time * 3.5));
    col += smoothstep(0.55, 0.9, s) * fall * 0.35;

    finalColor = vec4(col, water);
}
