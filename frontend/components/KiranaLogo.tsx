export function KiranaLogo({ compact = false }: { compact?: boolean }) {
  return <div className="flex items-center gap-3">
    <svg aria-label="Kirana Logistic Group" className="h-10 w-10 shrink-0" viewBox="0 0 48 48" role="img">
      <defs><linearGradient id="kirana-mark" x1="4" x2="44" y1="4" y2="44" gradientUnits="userSpaceOnUse"><stop stopColor="#0b5f5a"/><stop offset="1" stopColor="#d7a53a"/></linearGradient></defs>
      <path fill="url(#kirana-mark)" d="M7 6h11v13.5L31 6h10.5L27.4 22.8 42 42H30.3L18 25.5V42H7V6Z"/>
      <path fill="#fff" d="M13 12h4v9.4l11.5-9.4h5.4L18 25.2V17h-5v-5Z" opacity=".92"/>
    </svg>
    {!compact && <div className="leading-tight"><p className="text-base font-bold tracking-tight text-kirana-navy">KIRANA</p><p className="text-[10px] font-semibold tracking-[0.18em] text-kirana-gold">LOGISTIC GROUP</p></div>}
  </div>;
}
