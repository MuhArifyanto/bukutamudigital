import React, { useState, useEffect } from 'react';
import { Terminal, Shield, Cpu, Code, Mail, Volume2, VolumeX, Menu, X, Activity } from 'lucide-react';

interface NavbarProps {
  activeSection: string;
  setActiveSection: (section: string) => void;
}

export const Navbar: React.FC<NavbarProps> = ({ activeSection, setActiveSection }) => {
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [isScrolled, setIsScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const playClickSound = () => {
    if (!audioEnabled) return;
    try {
      const audioCtx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(800, audioCtx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(400, audioCtx.currentTime + 0.05);
      gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.05);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + 0.05);
    } catch {
      // Audio fallback
    }
  };

  const navItems = [
    { id: 'combat-engine', label: 'COMBAT ENGINE', icon: Shield },
    { id: 'projects', label: 'PROJECTS', icon: Cpu },
    { id: 'architecture', label: 'ARCHITECTURE', icon: Activity },
    { id: 'code-sandbox', label: 'CODE PATTERNS', icon: Code },
    { id: 'contact', label: 'TERMINAL', icon: Terminal },
  ];

  const handleNavClick = (id: string) => {
    playClickSound();
    setActiveSection(id);
    setMobileMenuOpen(false);
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
      isScrolled ? 'bg-[#06080e]/90 backdrop-blur-md border-b border-cyan-500/20 py-3 shadow-[0_4px_30px_rgba(0,0,0,0.8)]' : 'bg-transparent py-5'
    }`}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between">
          
          {/* Logo & HUD Status */}
          <div className="flex items-center space-x-3 cursor-pointer" onClick={() => handleNavClick('hero')}>
            <div className="relative w-10 h-10 bg-[#0c101c] border border-cyan-500/50 rounded flex items-center justify-center glow-cyan group">
              <span className="font-mono text-cyan-400 font-bold text-lg group-hover:scale-110 transition-transform">VX</span>
              <div className="absolute -top-1 -right-1 w-2 h-2 bg-cyan-400 rounded-full animate-ping"></div>
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-mono font-bold tracking-wider text-white text-base">VANGUARD<span className="text-cyan-400">_DEV</span></span>
                <span className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-mono bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 rounded">
                  v2.4.0
                </span>
              </div>
              <p className="text-[10px] font-mono text-slate-400 flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                SYS_STATUS: ONLINE (120Hz)
              </p>
            </div>
          </div>

          {/* Desktop Nav Items */}
          <div className="hidden lg:flex items-center space-x-1 bg-[#0c101c]/80 border border-slate-800/80 p-1 rounded-lg backdrop-blur">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => handleNavClick(item.id)}
                  className={`flex items-center space-x-2 px-3.5 py-1.5 rounded text-xs font-mono tracking-wider transition-all duration-200 ${
                    isActive 
                      ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 glow-cyan font-bold' 
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-cyan-400 animate-pulse' : 'text-slate-500'}`} />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>

          {/* Controls: Audio Toggle & Mobile Menu */}
          <div className="flex items-center space-x-3">
            <button
              onClick={() => {
                setAudioEnabled(!audioEnabled);
                playClickSound();
              }}
              className="p-2 bg-[#0c101c] border border-slate-800 hover:border-cyan-500/40 rounded text-slate-400 hover:text-cyan-400 transition-colors"
              title={audioEnabled ? "Mute HUD Telemetry Audio" : "Enable HUD Telemetry Audio"}
            >
              {audioEnabled ? <Volume2 className="w-4 h-4 text-cyan-400" /> : <VolumeX className="w-4 h-4 text-slate-600" />}
            </button>

            {/* Mobile hamburger toggle */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="lg:hidden p-2 bg-[#0c101c] border border-slate-800 rounded text-slate-300 hover:text-cyan-400"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation Drawer */}
        {mobileMenuOpen && (
          <div className="lg:hidden mt-3 p-4 bg-[#0c101c] border border-cyan-500/30 rounded-lg shadow-2xl space-y-2 font-mono">
            {navItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => handleNavClick(item.id)}
                  className={`w-full flex items-center space-x-3 px-4 py-2.5 rounded text-xs transition-all ${
                    isActive ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/50 font-bold' : 'text-slate-300 hover:bg-slate-800'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </nav>
  );
};
