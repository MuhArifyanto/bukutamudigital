import React, { useState } from 'react';
import { Terminal, Send, Mail, FileText, CheckCircle2, Globe, Shield, Code2, Share2 } from 'lucide-react';

export const ContactSection: React.FC = () => {
  const [formData, setFormData] = useState({
    name: '',
    organization: '',
    email: '',
    message: ''
  });

  const [status, setStatus] = useState<'idle' | 'transmitting' | 'sent'>('idle');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.email || !formData.message) return;

    setStatus('transmitting');
    setTimeout(() => {
      setStatus('sent');
    }, 1200);
  };

  return (
    <section id="contact" className="py-24 relative bg-[#06080e] border-t border-slate-800/80 scanlines">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-16">
        
        {/* Section Header */}
        <div className="text-center space-y-4 max-w-3xl mx-auto">
          <div className="inline-flex items-center space-x-2 px-3 py-1 bg-cyan-500/10 border border-cyan-500/30 rounded-full text-xs font-mono text-cyan-400">
            <Terminal className="w-3.5 h-3.5" />
            <span>ENCRYPTED TRANSMISSION PROTOCOL</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-extrabold text-white font-display tracking-tight">
            ESTABLISH <span className="text-cyan-400 text-glow-cyan">TRANSMISSION</span>
          </h2>
          <p className="text-slate-400 text-sm sm:text-base">
            Open for Lead Gameplay Programming roles, Combat Systems Consulting, and Senior Engine Architecture opportunities.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
          
          {/* Left Column: Direct Links & Profiles */}
          <div className="lg:col-span-5 space-y-6 font-mono">
            
            <div className="bg-[#0c101c] border border-cyan-500/30 rounded-xl p-6 glow-cyan space-y-6 hud-box">
              <div className="border-b border-slate-800 pb-3">
                <span className="text-[10px] text-cyan-400 uppercase tracking-widest">DIRECT COMMUNICATIONS</span>
                <h3 className="text-base font-bold text-white font-display">DEV NETWORK COORDINATES</h3>
              </div>

              {/* Direct Links List */}
              <div className="space-y-4 text-xs">
                
                <a 
                  href="mailto:contact@vanguard-gamedev.com" 
                  className="p-3 bg-[#05070d] border border-slate-800 hover:border-cyan-500/50 rounded-lg flex items-center space-x-3 text-slate-300 hover:text-cyan-400 transition-all group"
                >
                  <div className="p-2 bg-cyan-500/10 rounded text-cyan-400 group-hover:scale-110 transition-transform">
                    <Mail className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500">PRIMARY EMAIL</p>
                    <p className="font-bold">vanguard.gamedev@gmail.com</p>
                  </div>
                </a>

                <a 
                  href="https://github.com" 
                  target="_blank" 
                  rel="noreferrer"
                  className="p-3 bg-[#05070d] border border-slate-800 hover:border-purple-500/50 rounded-lg flex items-center space-x-3 text-slate-300 hover:text-purple-400 transition-all group"
                >
                  <div className="p-2 bg-purple-500/10 rounded text-purple-400 group-hover:scale-110 transition-transform">
                    <Code2 className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500">GITHUB REPOSITORIES</p>
                    <p className="font-bold">github.com/vanguard-gamedev</p>
                  </div>
                </a>

                <a 
                  href="https://linkedin.com" 
                  target="_blank" 
                  rel="noreferrer"
                  className="p-3 bg-[#05070d] border border-slate-800 hover:border-yellow-500/50 rounded-lg flex items-center space-x-3 text-slate-300 hover:text-yellow-400 transition-all group"
                >
                  <div className="p-2 bg-yellow-500/10 rounded text-yellow-400 group-hover:scale-110 transition-transform">
                    <Share2 className="w-4 h-4" />
                  </div>
                  <div>
                    <p className="text-[10px] text-slate-500">PROFESSIONAL NETWORK</p>
                    <p className="font-bold">linkedin.com/in/game-developer</p>
                  </div>
                </a>

              </div>

              {/* Resume Download CTA */}
              <div className="pt-2 border-t border-slate-800/80">
                <a
                  href="#resume"
                  onClick={(e) => {
                    e.preventDefault();
                    alert("Simulated PDF Download: Systems Architect Resume 2024.pdf");
                  }}
                  className="w-full py-3 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-bold text-xs rounded shadow glow-cyan flex items-center justify-center space-x-2 transition-all"
                >
                  <FileText className="w-4 h-4" />
                  <span>DOWNLOAD_RESUME_CV.PDF</span>
                </a>
              </div>

            </div>

          </div>

          {/* Right Column: Cyberpunk Interactive Terminal Form */}
          <div className="lg:col-span-7">
            <div className="bg-[#0c101c] border border-slate-800 rounded-xl p-8 space-y-6 font-mono shadow-2xl hud-box">
              
              <div className="flex items-center justify-between border-b border-slate-800 pb-4">
                <div className="flex items-center space-x-2">
                  <Terminal className="w-4 h-4 text-cyan-400" />
                  <span className="text-xs text-slate-200 font-bold">TERMINAL TRANSMISSION INPUT</span>
                </div>
                <span className="text-[10px] text-cyan-400 bg-cyan-500/10 px-2 py-0.5 rounded border border-cyan-500/30">
                  ENCRYPTION: AES-256
                </span>
              </div>

              {status === 'sent' ? (
                <div className="py-12 text-center space-y-4">
                  <div className="w-16 h-16 bg-emerald-500/10 border border-emerald-500/40 text-emerald-400 rounded-full flex items-center justify-center mx-auto animate-bounce">
                    <CheckCircle2 className="w-8 h-8" />
                  </div>
                  <h3 className="text-xl font-bold text-white font-display">TRANSMISSION ACKNOWLEDGED</h3>
                  <p className="text-xs text-slate-300 max-w-md mx-auto font-sans">
                    Thank you. Your message has been received into the queue. I will respond within 24 hours.
                  </p>
                  <button
                    onClick={() => {
                      setStatus('idle');
                      setFormData({ name: '', organization: '', email: '', message: '' });
                    }}
                    className="px-6 py-2 bg-slate-800 hover:bg-slate-700 text-xs text-cyan-400 rounded border border-slate-700"
                  >
                    SEND_ANOTHER_TRANSMISSION
                  </button>
                </div>
              ) : (
                <form onSubmit={handleSubmit} className="space-y-4 text-xs">
                  
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <label className="text-slate-400">CALLSIGN / NAME *</label>
                      <input
                        type="text"
                        required
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="e.g. Lead Producer / Alex Vance"
                        className="w-full bg-[#05070d] border border-slate-800 focus:border-cyan-400 rounded p-3 text-slate-200 outline-none transition-colors"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="text-slate-400">STUDIO / ORGANIZATION</label>
                      <input
                        type="text"
                        value={formData.organization}
                        onChange={(e) => setFormData({ ...formData, organization: e.target.value })}
                        placeholder="e.g. Respawn / CD Projekt Red / Indie Studio"
                        className="w-full bg-[#05070d] border border-slate-800 focus:border-cyan-400 rounded p-3 text-slate-200 outline-none transition-colors"
                      />
                    </div>
                  </div>

                  <div className="space-y-1">
                    <label className="text-slate-400">RETURN EMAIL ADDRESS *</label>
                    <input
                      type="email"
                      required
                      value={formData.email}
                      onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                      placeholder="e.g. alex@gamestudio.com"
                      className="w-full bg-[#05070d] border border-slate-800 focus:border-cyan-400 rounded p-3 text-slate-200 outline-none transition-colors"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-slate-400">TRANSMISSION BODY / INQUIRY *</label>
                    <textarea
                      required
                      rows={5}
                      value={formData.message}
                      onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                      placeholder="Details regarding your project scope, combat system requirements, or position..."
                      className="w-full bg-[#05070d] border border-slate-800 focus:border-cyan-400 rounded p-3 text-slate-200 outline-none transition-colors"
                    ></textarea>
                  </div>

                  <button
                    type="submit"
                    disabled={status === 'transmitting'}
                    className="w-full py-3.5 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs rounded glow-cyan flex items-center justify-center space-x-2 transition-all disabled:opacity-50"
                  >
                    {status === 'transmitting' ? (
                      <span>TRANSMITTING_PACKETS...</span>
                    ) : (
                      <>
                        <Send className="w-4 h-4" />
                        <span>TRANSMIT_MESSAGE</span>
                      </>
                    )}
                  </button>

                </form>
              )}

            </div>
          </div>

        </div>

      </div>
    </section>
  );
};
