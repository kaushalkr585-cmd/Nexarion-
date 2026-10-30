import React, { useEffect, useRef } from "react";
import type { WaveState } from "../../types";

interface LiquidWaveBackgroundProps {
  state?: WaveState;
  className?: string;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  baseAlpha: number;
}

export const LiquidWaveBackground: React.FC<LiquidWaveBackgroundProps> = ({
  state = "idle",
  className = "",
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<WaveState>(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;

    let animFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const updateSize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.scale(dpr, dpr);
    };

    updateSize();
    window.addEventListener("resize", updateSize);

    const particleCount = prefersReducedMotion ? 25 : 60;
    const particles: Particle[] = [];
    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        size: Math.random() * 1.5 + 0.5,
        alpha: Math.random() * 0.4 + 0.1,
        baseAlpha: Math.random() * 0.4 + 0.1,
      });
    }

    let time = 0;
    let pulseProgress = 0;
    let isDocumentVisible = true;

    const render = () => {

      if (!isDocumentVisible) {
        animFrameId = requestAnimationFrame(render);
        return;
      }

      const currentState = stateRef.current;

      let speed = prefersReducedMotion ? 0.003 : 0.006;
      let amplitude = 28;
      let waveCount = 3;
      let particleBoost = 1.0;
      let highlightPulse = 0;

      if (currentState === "receiving") {
        speed = 0.012;
        amplitude = 36;
        particleBoost = 1.8;
      } else if (currentState === "thinking") {
        speed = 0.016;
        amplitude = 44;
        particleBoost = 2.2;
        highlightPulse = Math.sin(time * 3) * 0.15;
      } else if (currentState === "reviewing") {
        speed = 0.02;
        amplitude = 50;
        waveCount = 5;
        particleBoost = 2.5;
        highlightPulse = (Math.sin(time * 4) + Math.cos(time * 2.5)) * 0.12;
      } else if (currentState === "responding") {
        speed = 0.009;
        amplitude = 32;
        pulseProgress = Math.min(pulseProgress + 0.02, 1);
        highlightPulse = (1 - pulseProgress) * 0.25;
      } else if (currentState === "error") {
        speed = 0.004;
        amplitude = 20;
        particleBoost = 0.6;
      } else {

        pulseProgress = 0;
      }

      time += speed;

      ctx.fillStyle = "#000000";
      ctx.fillRect(0, 0, width, height);

      const bgGrad = ctx.createRadialGradient(
        width * 0.65,
        height * 0.35,
        80,
        width * 0.5,
        height * 0.5,
        Math.max(width, height) * 0.8
      );
      bgGrad.addColorStop(0, `rgba(60, 60, 72, ${0.14 + highlightPulse})`);
      bgGrad.addColorStop(0.45, "rgba(22, 22, 28, 0.07)");
      bgGrad.addColorStop(1, "rgba(0, 0, 0, 0.98)");
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, width, height);

      const baseY = height * 0.65;

      for (let w = 0; w < waveCount; w++) {
        ctx.beginPath();
        ctx.moveTo(0, height);

        const waveOffset = w * 1.8;
        const layerAmp = amplitude * (1 - w * 0.18);
        const yOffset = baseY + (w - 1) * 35;

        for (let x = 0; x <= width; x += 12) {
          const normX = x / width;

          const sin1 = Math.sin(normX * 4 + time * 1.5 + waveOffset);
          const sin2 = Math.cos(normX * 7 - time * 1.2 + waveOffset * 0.5) * 0.5;
          const sin3 = Math.sin(normX * 12 + time * 2.0) * 0.2;

          let y = yOffset + (sin1 + sin2 + sin3) * layerAmp;

          if (currentState === "reviewing") {
            const multiAgentPulse = Math.sin(normX * 20 + time * 3 + w) * 8;
            y += multiAgentPulse;
          }

          if (x === 0) {
            ctx.lineTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }

        ctx.lineTo(width, height);
        ctx.closePath();

        const waveGrad = ctx.createLinearGradient(0, yOffset - layerAmp, 0, height);
        const baseAlpha = 0.06 + w * 0.035 + (highlightPulse > 0 ? highlightPulse * 0.3 : 0);
        waveGrad.addColorStop(0, `rgba(210, 215, 225, ${baseAlpha * 1.6})`);
        waveGrad.addColorStop(0.3, `rgba(140, 145, 155, ${baseAlpha})`);
        waveGrad.addColorStop(0.8, "rgba(30, 30, 35, 0.02)");
        waveGrad.addColorStop(1, "rgba(0, 0, 0, 0.8)");

        ctx.fillStyle = waveGrad;
        ctx.fill();

        ctx.beginPath();
        for (let x = 0; x <= width; x += 12) {
          const normX = x / width;
          const sin1 = Math.sin(normX * 4 + time * 1.5 + waveOffset);
          const sin2 = Math.cos(normX * 7 - time * 1.2 + waveOffset * 0.5) * 0.5;
          const sin3 = Math.sin(normX * 12 + time * 2.0) * 0.2;
          const y = yOffset + (sin1 + sin2 + sin3) * layerAmp;

          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.strokeStyle = `rgba(255, 255, 255, ${0.12 + (w === 0 ? 0.1 : 0) + highlightPulse * 0.35})`;
        ctx.lineWidth = w === 0 ? 1.5 : 0.8;
        ctx.stroke();
      }

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.x += p.vx * particleBoost;
        p.y += p.vy * particleBoost;

        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        p.alpha = p.baseAlpha + Math.sin(time * 2 + i) * 0.1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255, 255, 255, ${Math.max(0.05, Math.min(p.alpha, 0.5))})`;
        ctx.fill();
      }

      animFrameId = requestAnimationFrame(render);
    };

    const handleVisibility = () => {
      isDocumentVisible = !document.hidden;
      if (!document.hidden) {
        cancelAnimationFrame(animFrameId);
        animFrameId = requestAnimationFrame(render);
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);

    animFrameId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animFrameId);
      window.removeEventListener("resize", updateSize);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={`fixed inset-0 pointer-events-none z-0 ${className}`}
      aria-hidden="true"
    />
  );
};
