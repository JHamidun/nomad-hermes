import * as React from 'react'
import { useEffect, useRef, useState } from 'react'

import { HelpCircle } from '@/lib/icons'
import { cn } from '@/lib/utils'

import { Popover, PopoverContent, PopoverTrigger } from './popover'

export interface HelpTipProps {
  text?: React.ReactNode
  title?: string
  label?: string
  side?: 'top' | 'right' | 'bottom' | 'left'
  align?: 'center' | 'end' | 'start'
  className?: string
}

/**
 * Beginner-help affordance: a small "?" button that reveals a 1-3 sentence
 * plain-language explainer on hover (pointer) or click/tap (touch).
 * Renders nothing when `text` is empty or undefined.
 */
export function HelpTip({
  text,
  title,
  label = 'What is this?',
  side = 'top',
  align = 'center',
  className
}: HelpTipProps) {
  const [open, setOpen] = useState(false)
  const closeTimer = useRef<number | null>(null)

  const cancelClose = () => {
    if (closeTimer.current !== null) {
      window.clearTimeout(closeTimer.current)
      closeTimer.current = null
    }
  }

  const scheduleClose = () => {
    cancelClose()
    closeTimer.current = window.setTimeout(() => setOpen(false), 150)
  }

  useEffect(() => cancelClose, [])

  if (!text) {
    return null
  }

  return (
    <Popover onOpenChange={setOpen} open={open}>
      <PopoverTrigger asChild>
        <button
          aria-label={title ? `${label}: ${title}` : label}
          className={cn(
            'help-tip-trigger inline-flex size-4 shrink-0 cursor-help items-center justify-center rounded-full align-middle text-(--ui-text-tertiary) outline-none transition-opacity duration-150 hover:text-(--ui-accent) focus-visible:text-(--ui-accent) focus-visible:ring-2 focus-visible:ring-ring/50 data-[state=open]:text-(--ui-accent)',
            className
          )}
          data-slot="help-tip-trigger"
          onClick={() => {
            cancelClose()
            setOpen(current => !current)
          }}
          onMouseEnter={() => {
            cancelClose()
            setOpen(true)
          }}
          onMouseLeave={scheduleClose}
          type="button"
        >
          <HelpCircle aria-hidden="true" className="size-3.5" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align={align}
        className="w-64 px-3 py-2.5"
        data-slot="help-tip-content"
        onMouseEnter={cancelClose}
        onMouseLeave={scheduleClose}
        onOpenAutoFocus={event => event.preventDefault()}
        side={side}
        sideOffset={8}
      >
        {title ? <div className="mb-1 text-xs font-semibold text-foreground">{title}</div> : null}
        <p className="m-0 text-xs leading-relaxed text-(--ui-text-secondary)">{text}</p>
      </PopoverContent>
    </Popover>
  )
}
