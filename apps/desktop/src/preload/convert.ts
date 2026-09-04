import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'

/**
 * Preload of the hidden DWG converter window (`apps/desktop/src/main/convert`).
 *
 * It is deliberately *not* the main preload: the converter page gets one
 * channel pair and nothing else — no engine connection, no file dialogs — so a
 * defect in the GPL parsing path cannot reach the rest of the app's IPC
 * surface. `contextIsolation: true` and `sandbox: true` still apply
 * (CLAUDE.md rule 9).
 *
 * Channel names are duplicated from `src/main/convert/protocol.ts` on purpose:
 * main and preload are separate build entries.
 */

const REQUEST_CHANNEL = 'halocad:convert:request'
const RESULT_CHANNEL = 'halocad:convert:result'
const READY_CHANNEL = 'halocad:convert:ready'

export interface ConvertRequest {
  requestId: string
  bytes: Uint8Array
  name: string
}

export interface ConvertReply {
  requestId: string
  ok: boolean
  dxf?: string
  entityCount?: number
  warnings: string[]
  error?: string
}

const convertApi = {
  /** Registers the page's handler and tells main it may start sending work. */
  onRequest: (callback: (request: ConvertRequest) => void): void => {
    ipcRenderer.on(REQUEST_CHANNEL, (_event: IpcRendererEvent, request: ConvertRequest) => {
      callback(request)
    })
    ipcRenderer.send(READY_CHANNEL)
  },
  reply: (reply: ConvertReply): void => {
    ipcRenderer.send(RESULT_CHANNEL, reply)
  },
  /** Root the viewer worker/wasm assets are served from. */
  assetsBase: (): string => 'halocad://app/viewer',
}

export type HaloConvertApi = typeof convertApi

contextBridge.exposeInMainWorld('halocadConvert', convertApi)
