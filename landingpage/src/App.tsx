import React, { useState, useEffect } from 'react';
import { Send, Moon } from 'lucide-react';

const GridBackground = () => {
  const [cells, setCells] = useState(2000);

  useEffect(() => {
    const calculateCells = () => {
      const cols = Math.floor((window.innerWidth + 128) / 64);
      const rows = Math.floor((window.innerHeight + 128) / 64);
      setCells(cols * rows);
    };
    
    calculateCells();
    window.addEventListener('resize', calculateCells);
    return () => window.removeEventListener('resize', calculateCells);
  }, []);

  return (
    <div className="fixed -inset-[64px] z-0 overflow-hidden pointer-events-auto flex flex-wrap content-start">
      {Array.from({ length: cells }).map((_, i) => (
        <div 
          key={i} 
          className="w-[64px] h-[64px] border-r border-b border-black/[0.06] hover:bg-black/[0.04] transition-colors duration-300 ease-out" 
        />
      ))}
    </div>
  );
};

const Navbar = () => {
  return (
    <nav className="flex items-center justify-between px-8 py-5 border-b border-black/[0.05] bg-white/80 backdrop-blur-md pointer-events-auto relative z-20">
      <div className="flex items-center gap-3">
        <div className="w-6 h-6 bg-black flex items-center justify-center rounded-none">
          <div className="w-2 h-2 bg-white rounded-full" />
        </div>
        <span className="text-xl font-semibold tracking-tight">komosis</span>
      </div>
      
      <div className="flex items-center gap-8">
        <a href="#" className="text-sm text-gray-600 hover:text-black transition-colors">Team</a>
        <button className="relative overflow-hidden bg-black text-white px-6 py-2.5 text-sm font-medium transition-colors rounded-none group">
          <span className="relative z-10">GitHub</span>
          <div className="absolute inset-0 bg-gray-800 transform scale-x-0 origin-left group-hover:scale-x-100 transition-transform duration-300 ease-out" />
        </button>
      </div>
    </nav>
  );
};

const BrowserMockup = () => {
  const words = ['Assistant', 'Auto-Heal', 'Fix'];
  const [currentWordIndex, setCurrentWordIndex] = useState(0);
  const [currentText, setCurrentText] = useState('');
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    const typeSpeed = isDeleting ? 50 : 100;
    const word = words[currentWordIndex];

    const timer = setTimeout(() => {
      if (!isDeleting && currentText === word) {
        // Pause before deleting
        setTimeout(() => setIsDeleting(true), 2000);
      } else if (isDeleting && currentText === '') {
        // Move to next word
        setIsDeleting(false);
        setCurrentWordIndex((prev) => (prev + 1) % words.length);
      } else {
        // Type or delete characters
        const nextText = isDeleting
          ? word.substring(0, currentText.length - 1)
          : word.substring(0, currentText.length + 1);
        setCurrentText(nextText);
      }
    }, typeSpeed);

    return () => clearTimeout(timer);
  }, [currentText, isDeleting, currentWordIndex]);

  return (
    <div className="w-full max-w-4xl bg-white border border-black/[0.1] shadow-2xl shadow-black/10 flex flex-col rounded-none relative z-20">
      {/* Browser Header */}
      <div className="h-12 border-b border-black/[0.1] bg-gray-50 flex items-center px-4 gap-4">
        <div className="flex gap-2">
          <div className="w-3 h-3 rounded-full bg-[#ff5f56]" />
          <div className="w-3 h-3 rounded-full bg-[#ffbd2e]" />
          <div className="w-3 h-3 rounded-full bg-[#27c93f]" />
        </div>
        <div className="flex-grow flex justify-center">
          <div className="bg-white text-gray-500 text-xs px-4 py-1.5 border border-black/[0.1] w-64 text-center font-mono rounded-none shadow-sm">
            komosis.ai
          </div>
        </div>
        <div className="w-12" /> {/* Spacer for balance */}
      </div>
      
      {/* Browser Content */}
      <div className="px-8 py-24 md:py-32 flex flex-col items-center text-center relative overflow-hidden">
        {/* Subtle background glow */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-purple-500/10 blur-[120px] rounded-full pointer-events-none" />
        
        <h1 className="text-4xl md:text-6xl font-bold tracking-tight mb-6 z-10 text-black">
          Autonomous <br className="hidden md:block" />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-[#9d4edd] via-[#c77dff] to-[#72efdd]">
            CI/CD {currentText}
            <span className="inline-block w-[3px] h-[1em] bg-black ml-1 animate-pulse align-middle" />
          </span>
        </h1>
        
        <p className="text-gray-600 text-lg md:text-xl max-w-2xl mb-12 z-10">
          Detect, fix, and verify code issues automatically in your development pipeline.
        </p>
        
        <div className="w-full max-w-xl flex flex-col gap-3 z-10">
          <label className="text-sm text-gray-600 font-medium text-left">Paste your repository link</label>
          <div className="relative flex items-center group">
            <input 
              type="text" 
              placeholder="https://github.com/username/repository"
              className="w-full bg-white border border-black/[0.1] rounded-none py-4 pl-4 pr-16 text-black placeholder:text-gray-400 focus:outline-none focus:border-black/[0.3] transition-all font-mono text-sm shadow-sm"
            />
            <button className="absolute right-2 w-10 h-10 bg-black text-white flex items-center justify-center hover:bg-gray-800 transition-colors rounded-none">
              <Send size={16} className="ml-0.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default function App() {
  return (
    <div className="min-h-screen bg-white text-black font-sans relative selection:bg-purple-500/30 overflow-hidden">
      <GridBackground />
      
      <div className="relative z-10 flex flex-col min-h-screen pointer-events-none">
        <Navbar />
        <main className="flex-grow flex items-center justify-center p-6 pointer-events-none">
          <div className="pointer-events-auto w-full max-w-4xl">
            <BrowserMockup />
          </div>
        </main>
      </div>

      <button className="fixed bottom-6 right-6 w-10 h-10 border border-black/[0.1] bg-white flex items-center justify-center text-gray-500 hover:text-black hover:bg-black/[0.05] transition-colors z-50 rounded-none pointer-events-auto">
        <Moon size={18} />
      </button>
    </div>
  );
}
