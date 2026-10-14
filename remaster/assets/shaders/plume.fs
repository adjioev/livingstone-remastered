#version 330
// Volcano plume: a widening, wind-bent column of rolling noise, snapped to the art grid.
in vec2 fragTexCoord;
out vec4 finalColor;

uniform float time;
uniform vec2 size;      // quad size in canvas px
uniform float pixel;    // art pixel size in canvas px
uniform float seed;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int k = 0; k < 5; k++) { v += a * vnoise(p); p = p * 2.07 + vec2(13.0, 7.0); a *= 0.5; }
    return v;
}

void main() {
    // snap to the art pixel grid
    vec2 px = floor(fragTexCoord * size / pixel) * pixel + pixel * 0.5;
    vec2 uv = px / size;                       // 0..1, y down
    float h = 1.0 - uv.y;                      // height above the crater, 0..1
    float crater = 0.18;                       // crater x in the quad
    // the column bends with the wind and wobbles slowly
    float centre = crater + 0.42 * pow(h, 1.7) + 0.03 * sin(time * 0.4 + h * 5.0 + seed);
    float width = 0.05 + 0.30 * h;
    // rolling noise moving up the column
    vec2 q = vec2((uv.x - centre) * 4.0, h * 4.0 - time * 0.25 + seed);   // same scale both ways: puffy, not streaky
    float n = fbm(q + vec2(fbm(q * 0.8 + time * 0.04), 0.0) * 0.8);
    float shape = 1.0 - smoothstep(0.45, 1.1, abs(uv.x - centre) / width + (0.5 - n) * 1.1);
    float dens = shape * smoothstep(0.0, 0.06, h) * (1.0 - smoothstep(0.55, 1.0, h));
    dens *= smoothstep(0.2, 0.55, n + 0.12);
    float edge = smoothstep(0.0, 0.12, uv.x) * smoothstep(0.0, 0.12, 1.0 - uv.x) * smoothstep(0.0, 0.15, uv.y);
    float a = clamp(dens * 1.1 * edge, 0.0, 0.9);
    // light grey, a little darker inside the folds; quantized to a few tones
    float tone = floor((0.72 + 0.28 * n) * 5.0) / 5.0;
    vec3 col = mix(vec3(0.58, 0.57, 0.6), vec3(0.95, 0.95, 0.96), tone);
    a = floor(a * 6.0) / 6.0;
    finalColor = vec4(col, a);
}
