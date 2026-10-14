#version 330
// Crystal glow: the background's own colour added back where the glow mask is set,
// pulsing with a phase that varies across the screen, plus brief twinkles.
in vec2 fragTexCoord;
out vec4 finalColor;

uniform sampler2D texture0;   // room background
uniform sampler2D glowMask;   // crystals, blurred
uniform float time;
uniform float flicker;        // 1: fire (fast irregular flicker), 0: crystal (slow pulse)

float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}

void main() {
    vec2 uv = fragTexCoord;
    float m = texture(glowMask, uv).r;
    if (m < 0.01) { finalColor = vec4(0.0); return; }
    vec3 col = texture(texture0, uv).rgb;
    float phase = vnoise(uv * vec2(14.0, 8.0)) * 6.28;
    float pulse = 0.5 + 0.5 * sin(time * 1.4 + phase);
    float tw = smoothstep(0.93, 1.0, vnoise(uv * vec2(60.0, 34.0) + vec2(time * 0.7, 0.0)));
    vec3 glow = (col * 1.2 + vec3(0.15, 0.2, 0.3)) * m * (0.25 + 0.55 * pulse) + vec3(tw * m);
    if (flicker > 0.5) {
        float f = vnoise(vec2(uv.x * 40.0, uv.y * 20.0 - time * 6.0)) * 0.6 + 0.4 * sin(time * 13.0 + phase);
        glow = col * vec3(1.0, 0.75, 0.4) * m * clamp(0.15 + 0.6 * f, 0.0, 1.0);
    }
    finalColor = vec4(glow, 1.0);
}
