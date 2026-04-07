import fp from 'fastify-plugin'
import { FastifyPluginAsync } from 'fastify'
import mongoose from 'mongoose'

const mongoPlugin: FastifyPluginAsync = fp(async (app) => {
  const url = process.env.MONGO_URL || 'mongodb://lab:labpass@mongodb:27017/adlab?authSource=admin'
  await mongoose.connect(url)
  app.addHook('onClose', async () => { await mongoose.disconnect() })
  app.log.info('MongoDB connected')
})

export { mongoPlugin }
