#version 300 es
precision highp float;

in vec2 v_uv;
out vec4 fragColor;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_hue;
uniform float u_volume;
uniform float u_activity;
uniform float u_swirl;
uniform int u_blob_count;

vec3 hsv2rgb(vec3 c) {
  vec3 p = abs(fract(c.xxx + vec3(0.0, 0.6666667, 0.3333333)) * 6.0 - 3.0);
  return c.z * mix(vec3(1.0), clamp(p - 1.0, 0.0, 1.0), c.y);
}

float hash(float n) {
  return fract(sin(n) * 43758.5453123);
}

vec2 blobPosition(int i, float t) {
  float fi = float(i);
  float seed = hash(fi * 12.9898);
  float seed2 = hash(fi * 78.233);
  float seed3 = hash(fi * 39.425);

  float speed = (0.12 + seed * 0.1) * u_activity;
  float ax = 0.48 + seed * 0.38;
  float ay = 0.42 + seed2 * 0.34;
  float phase = seed3 * 6.2831853;

  float px = sin(t * speed + phase) * ax;
  float py = cos(t * speed * 0.79 + phase * 1.23) * ay;

  px += sin(t * 0.19 + u_swirl + fi * 0.55) * 0.11;
  py += cos(t * 0.16 + u_swirl * 0.85 + fi * 0.72) * 0.1;

  float burst = u_volume * 0.22;
  px *= 1.0 + burst;
  py *= 1.0 + burst;

  return vec2(px, py);
}

float blobRadius(int i, float t) {
  float fi = float(i);
  float seed = hash(fi * 45.164);
  float base = 0.11 + seed * 0.09;
  float pulse = 0.028 * sin(t * 2.1 + seed * 18.0);
  return base + pulse + u_volume * 0.07;
}


float metaball(vec2 p, vec2 center, float radius) {
  vec2 d = p - center;
  float r2 = radius * radius;
  return r2 / (dot(d, d) + r2 * 0.025);
}

float field(vec2 p, float t) {
  float sum = 0.0;
  for (int i = 0; i < 32; i++) {
    if (i >= u_blob_count) break;
    vec2 c = blobPosition(i, t);
    float r = blobRadius(i, t);
    sum += metaball(p, c, r);
  }
  return sum;
}

void main() {
  vec2 uv = (gl_FragCoord.xy / u_resolution) * 2.0 - 1.0;
  uv.x *= u_resolution.x / u_resolution.y;

  float t = u_time;
  float warpAmt = 0.032 * u_activity * (1.0 + u_volume * 0.5);
  vec2 warp = vec2(
    sin(uv.y * 3.2 + t * 0.28 + u_swirl * 0.2),
    cos(uv.x * 2.6 - t * 0.24 + u_swirl * 0.16)
  ) * warpAmt;
  vec2 p = uv + warp;

  float f = field(p, t);

  float eps = 1.5 / min(u_resolution.x, u_resolution.y);
  float fx = field(p + vec2(eps, 0.0), t) - field(p - vec2(eps, 0.0), t);
  float fy = field(p + vec2(0.0, eps), t) - field(p - vec2(0.0, eps), t);
  vec3 normal = normalize(vec3(-fx, -fy, 0.014));

  float threshold = 0.62;
  float edge = 0.09 + u_volume * 0.06;
  float liquid = smoothstep(threshold - edge, threshold + edge * 0.5, f);
  float depth = smoothstep(threshold, threshold + 1.1, f);

  float flowHue = sin(t * 0.9 + p.x * 3.2 + p.y * 2.4) * 0.1;
  float blobMix = sin(t * 0.95 + f * 0.16 + p.x * 2.6) * 0.12
                + cos(t * 0.65 + u_swirl + p.y * 2.2) * 0.08;
  float hue = u_hue + depth * 0.22 + u_volume * 0.1 + flowHue + blobMix;

  vec3 colDeep = hsv2rgb(vec3(hue, 0.88, 0.32 + depth * 0.5));
  vec3 colShallow = hsv2rgb(vec3(hue + 0.12, 0.62, 0.68 + depth * 0.22));
  vec3 col = mix(colShallow, colDeep, depth);

  vec3 lightDir = normalize(vec3(0.35, 0.55, 0.85));
  float spec = pow(max(dot(normal, lightDir), 0.0), 24.0) * liquid;
  col += spec * vec3(0.85, 0.92, 1.0) * (0.35 + u_volume * 0.6);

  float fresnel = pow(1.0 - clamp(normal.z, 0.0, 1.0), 2.2);
  col += fresnel * hsv2rgb(vec3(hue + 0.18, 0.7, 0.6)) * liquid * 0.4;

  vec3 bg = vec3(0.012, 0.018, 0.048);
  vec3 finalCol = mix(bg, col, liquid);

  float vig = smoothstep(1.55, 0.35, length(uv));
  finalCol *= mix(0.92, 1.0, vig);

  fragColor = vec4(finalCol, 1.0);
}
