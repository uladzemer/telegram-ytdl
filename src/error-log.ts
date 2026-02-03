import { randomUUID } from "node:crypto"
import { ERRORS_FILE } from "./environment"
import { cutoffWithNotice } from "./util"
import { readJsonFile, writeFileAtomic } from "./file-util"

export type ErrorLogEntry = {
	id: string
	at: string
	userId?: number
	url?: string
	context?: string
	error?: string
}

const errorLogs: ErrorLogEntry[] = []
let errorLogsLoaded = false
let errorLogsSaveTimer: NodeJS.Timeout | undefined

export const loadErrorLogs = async () => {
	if (errorLogsLoaded) return
	errorLogsLoaded = true
	const data = await readJsonFile(
		ERRORS_FILE,
		{ errors: [] } as { errors?: ErrorLogEntry[] },
		{ label: "error logs", backupOnError: true },
	)
	if (Array.isArray(data?.errors)) {
		errorLogs.push(...data.errors)
	}
}

const saveErrorLogs = async () => {
	try {
		await writeFileAtomic(ERRORS_FILE, JSON.stringify({ errors: errorLogs }, null, 2))
	} catch (error) {
		console.error("Failed to save error logs:", error)
	}
}

const scheduleErrorLogsSave = () => {
	if (errorLogsSaveTimer) return
	errorLogsSaveTimer = setTimeout(() => {
		errorLogsSaveTimer = undefined
		saveErrorLogs().catch((error) => {
			console.error("Failed to save error logs:", error)
		})
	}, 2000)
}

export const logErrorEntry = async (
	entry: Omit<ErrorLogEntry, "id" | "at">,
) => {
	await loadErrorLogs()
	errorLogs.unshift({
		id: randomUUID(),
		at: new Date().toISOString(),
		...entry,
		error: entry.error ? cutoffWithNotice(String(entry.error)) : entry.error,
	})
	if (errorLogs.length > 300) errorLogs.length = 300
	scheduleErrorLogsSave()
	saveErrorLogs().catch((error) => {
		console.error("Failed to save error logs:", error)
	})
}

export const getErrorLogs = async () => {
	await loadErrorLogs()
	return errorLogs
}
