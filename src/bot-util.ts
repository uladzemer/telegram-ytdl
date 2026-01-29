import type { Chat, Message } from "grammy/types"

import { InlineKeyboard } from "grammy"
import { ADMIN_ID } from "./environment"
import { bot } from "./setup"
import { cutoffWithNotice } from "./util"
import { bold, code, mention } from "./constants"

type UserLike = {
	id: number
	username?: string
	first_name?: string
	last_name?: string
}

type MessageLike = {
	chat: { id: number }
	message_id: number
}

const formatUserMention = (user?: UserLike, chat?: Chat) => {
	if (user?.id) {
		const name = [user.first_name, user.last_name].filter(Boolean).join(" ")
		const label = name || (user.username ? `@${user.username}` : "user")
		const escaped = label
			.replace(/&/g, "&amp;")
			.replace(/</g, "&lt;")
			.replace(/>/g, "&gt;")
		return `<a href="tg://user?id=${user.id}">${escaped}</a>`
	}
	if (chat?.type === "private") {
		return mention("user", chat.id)
	}
	return code(`chat:${chat?.id ?? "unknown"}`)
}

const formatUserIdLink = (user?: UserLike) => {
	if (!user?.id) return "—"
	return `<a href="tg://user?id=${user.id}">${user.id}</a>`
}

export const deleteMessage = (message: Message) => {
	return bot.api.deleteMessage(message.chat.id, message.message_id)
}

export const errorMessage = (
	chat: Chat,
	error?: string,
	user?: UserLike,
	originalMessage?: MessageLike,
) => {
	if (chat.type !== "private") return

	const messageText = bold("Ошибка.")

	const tasks = [
		bot.api.sendMessage(chat.id, messageText, { parse_mode: "HTML" }),
	]

	const userIdLabel = user?.id ? ` (id: ${user.id})` : ""
	let adminMessage = `Ошибка в чате ${formatUserMention(user, chat)}${userIdLabel}`
	if (error) adminMessage += `\n\n${code(cutoffWithNotice(error))}`

	console.error("Error in chat", chat.id, error)

	const keyboard =
		user?.id && user.id !== ADMIN_ID
			? new InlineKeyboard().text("Ban user", `ban:${user.id}`)
			: undefined
	tasks.push(
		bot.api.sendMessage(ADMIN_ID, adminMessage, {
			parse_mode: "HTML",
			reply_markup: keyboard,
		}),
	)
	if (originalMessage) {
		tasks.push(
			bot.api.forwardMessage(
				ADMIN_ID,
				originalMessage.chat.id,
				originalMessage.message_id,
			),
		)
	}

	return Promise.all(tasks)
}

export const notifyAdminError = (
	chat: Chat,
	context: string,
	error?: string,
	user?: UserLike,
	originalMessage?: MessageLike,
) => {
	const userIdLabel = user?.id ? ` (id: ${user.id})` : ""
	let adminMessage = `Ошибка в чате ${formatUserMention(user, chat)}${userIdLabel}`
	if (context) adminMessage += `\n\n${code(cutoffWithNotice(context))}`
	if (error) adminMessage += `\n\n${code(cutoffWithNotice(error))}`
	const keyboard =
		user?.id && user.id !== ADMIN_ID
			? new InlineKeyboard().text("Ban user", `ban:${user.id}`)
			: undefined
	const tasks = [
		bot.api.sendMessage(ADMIN_ID, adminMessage, {
			parse_mode: "HTML",
			reply_markup: keyboard,
		}),
	]
	if (originalMessage) {
		tasks.push(
			bot.api.forwardMessage(
				ADMIN_ID,
				originalMessage.chat.id,
				originalMessage.message_id,
			),
		)
	}
	return Promise.all(tasks)
}
