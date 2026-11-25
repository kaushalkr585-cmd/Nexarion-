import React, { useState } from "react";

interface PasswordInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> {
  label?: string;
  labelClassName?: string;
  inputClassName?: string;
  toggleAriaLabel?: string;
}

export const PasswordInput: React.FC<PasswordInputProps> = ({
  label,
  labelClassName = "block text-xs font-mono text-neutral-400 mb-1.5",
  id,
  inputClassName = "",
  className = "",
  toggleAriaLabel = "Toggle password visibility",
  ...rest
}) => {
  const [visible, setVisible] = useState(false);

  return (
    <div className={className}>
      {label && (
        <label htmlFor={id} className={labelClassName}>
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        <input
          id={id}
          type={visible ? "text" : "password"}
          className={`w-full bg-black/70 border border-white/15 rounded-lg pl-3 pr-9 py-2 text-xs text-white placeholder-neutral-600 focus:outline-none focus:border-white/40 ${inputClassName}`}
          {...rest}
        />
        <button
          type="button"
          onClick={() => setVisible((prev) => !prev)}
          aria-label={visible ? "Hide password" : "Show password"}
          title={visible ? "Hide password" : "Show password"}
          data-password-visibility-toggle="true"
          className="absolute right-2 p-1 rounded-md text-neutral-400 hover:text-white hover:bg-white/10 transition-colors cursor-pointer"
        >
          {visible ? (
            <svg
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
              <line x1="1" y1="1" x2="23" y2="23" />
            </svg>
          ) : (
            <svg
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
};
