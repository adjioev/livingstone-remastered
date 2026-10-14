#version 330
// Drifting mist and clouds over a room background, only where the room is open air.
// Noise is computed here (no texture, so no tiling seams).
in vec2 fragTexCoord;
out vec4 finalColor;

uniform sampler2D texture0;   // air mask (white = open air), already blurred
uniform float time;
uniform vec4 mistColor;
uniform vec4 cloudColor;
uniform float mistCenter, mistWidth, mistStrength;
uniform float cloudCenter, cloudWidth, cloudStrength;

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }

float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}

float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int k = 0; k < 5; k++) { v += a * vnoise(p); p = p * 2.03 + vec2(17.0, 9.0); a *= 0.5; }
    return v;
}

float band(float y, float c, float w) { float d = (y - c) / w; return exp(-d * d); }

void main() {
    vec2 uv = fragTexCoord;
    vec2 p = vec2(uv.x * 16.0 / 9.0, uv.y);          // square noise cells
    float air = texture(texture0, uv).r;

    float m = fbm(p * vec2(2.2, 4.0) + vec2(time * 0.025, 0.0))
            + 0.5 * fbm(p * vec2(3.5, 6.0) - vec2(time * 0.015, time * 0.004));
    float mist = smoothstep(0.55, 1.05, m) * band(uv.y, mistCenter, mistWidth) * mistStrength;

    float c = fbm(p * vec2(2.5, 6.0) + vec2(time * 0.04, 3.0));
    float cloud = smoothstep(0.5, 0.8, c) * band(uv.y, cloudCenter, cloudWidth) * cloudStrength;

    float a = clamp((mist + cloud) * air, 0.0, 1.0);
    vec3 col = mix(mistColor.rgb, cloudColor.rgb, cloud / max(mist + cloud, 1e-4));
    finalColor = vec4(col, a);
}
