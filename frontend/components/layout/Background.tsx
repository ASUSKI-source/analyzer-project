"use client";

import { useAuth } from "@/contexts/AuthContext";

/**
 * Background video switcher.
 * 
 * To change videos: simply replace the files in /public:
 *   - /bg-login.mp4    → plays on the login/landing page
 *   - /bg-dashboard.mp4 → plays once authenticated or in guest mode
 * 
 * Falls back to /bg.mp4 if the specific files don't exist yet.
 */
export function Background() {
  const { user, isGuest } = useAuth();
  const isAuthenticated = !!user || isGuest;

  const videoSrc = isAuthenticated ? "/bg-dashboard.mp4" : "/bg-login.mp4";

  return (
    <div className="fixed inset-0 z-[-1] overflow-hidden bg-slate-950">
      {/* 
        Key forces React to unmount/remount the video element when 
        the source changes, ensuring the new video actually plays.
      */}
      <video
        key={videoSrc}
        autoPlay
        loop
        muted
        playsInline
        className="absolute inset-0 w-full h-full object-cover"
      >
        <source src={videoSrc} type="video/mp4" />
        {/* Fallback: tries the original bg.mp4 if the specific one is missing */}
        <source src="/bg.mp4" type="video/mp4" />
      </video>

      {/* Darkening Overlay: Ensures text and glass borders remain highly visible even on bright videos */}
      <div className="absolute inset-0 bg-black/50 mix-blend-multiply" />
      
      {/* Color Tint: Keeps the "Steel/Slate" theme subtly active over the specific video colors */}
      <div className="absolute inset-0 bg-[#0B0E14]/60 mix-blend-overlay" />

      {/* Subtle noise overlay to give the glass "texture" over the video */}
      <div 
        className="absolute inset-0 opacity-[0.05] pointer-events-none mix-blend-overlay"
        style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E")` }}
      />
    </div>
  );
}
