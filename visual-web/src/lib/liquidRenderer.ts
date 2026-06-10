import vertSource from "../shaders/liquid.vert.glsl?raw";
import fragSource from "../shaders/liquid.frag.glsl?raw";

function compileShader(gl: WebGL2RenderingContext, type: number, source: string): WebGLShader {
  const shader = gl.createShader(type);
  if (!shader) throw new Error("Не удалось создать шейдер");
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader) ?? "unknown";
    gl.deleteShader(shader);
    throw new Error(`Ошибка компиляции шейдера: ${log}`);
  }
  return shader;
}

function createProgram(gl: WebGL2RenderingContext, vert: string, frag: string): WebGLProgram {
  const program = gl.createProgram();
  if (!program) throw new Error("Не удалось создать программу");
  const vs = compileShader(gl, gl.VERTEX_SHADER, vert);
  const fs = compileShader(gl, gl.FRAGMENT_SHADER, frag);
  gl.attachShader(program, vs);
  gl.attachShader(program, fs);
  gl.linkProgram(program);
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const log = gl.getProgramInfoLog(program) ?? "unknown";
    gl.deleteProgram(program);
    throw new Error(`Ошибка линковки: ${log}`);
  }
  return program;
}

export interface LiquidDrawParams {
  time: number;
  hue: number;
  volume: number;
  activity: number;
  swirl: number;
}

export interface LiquidRenderer {
  resize(width: number, height: number): void;
  draw(params: LiquidDrawParams): void;
  destroy(): void;
}

export function createLiquidRenderer(
  canvas: HTMLCanvasElement,
  blobCount: number,
): LiquidRenderer {
  const gl = canvas.getContext("webgl2", { alpha: false, antialias: false });
  if (!gl) throw new Error("WebGL2 недоступен");

  const program = createProgram(gl, vertSource, fragSource);
  const quad = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quad);
  gl.bufferData(
    gl.ARRAY_BUFFER,
    new Float32Array([-1, -1, 1, -1, -1, 1, -1, 1, 1, -1, 1, 1]),
    gl.STATIC_DRAW,
  );

  const aPosition = gl.getAttribLocation(program, "a_position");
  gl.enableVertexAttribArray(aPosition);
  gl.vertexAttribPointer(aPosition, 2, gl.FLOAT, false, 0, 0);

  const uResolution = gl.getUniformLocation(program, "u_resolution");
  const uTime = gl.getUniformLocation(program, "u_time");
  const uHue = gl.getUniformLocation(program, "u_hue");
  const uVolume = gl.getUniformLocation(program, "u_volume");
  const uActivity = gl.getUniformLocation(program, "u_activity");
  const uSwirl = gl.getUniformLocation(program, "u_swirl");
  const uBlobCount = gl.getUniformLocation(program, "u_blob_count");

  let width = 0;
  let height = 0;
  const blobs = Math.max(8, Math.min(32, blobCount));

  return {
    resize(w: number, h: number) {
      width = Math.max(1, Math.floor(w));
      height = Math.max(1, Math.floor(h));
      canvas.width = width;
      canvas.height = height;
      gl.viewport(0, 0, width, height);
    },
    draw(params) {
      gl.clearColor(0.012, 0.018, 0.048, 1);
      gl.clear(gl.COLOR_BUFFER_BIT);

      gl.useProgram(program);
      gl.bindBuffer(gl.ARRAY_BUFFER, quad);

      gl.uniform2f(uResolution, width, height);
      gl.uniform1f(uTime, params.time);
      gl.uniform1f(uHue, params.hue);
      gl.uniform1f(uVolume, params.volume);
      gl.uniform1f(uActivity, params.activity);
      gl.uniform1f(uSwirl, params.swirl);
      gl.uniform1i(uBlobCount, blobs);

      gl.drawArrays(gl.TRIANGLES, 0, 6);
    },
    destroy() {
      gl.deleteBuffer(quad);
      gl.deleteProgram(program);
    },
  };
}
