package com.nico.gpx2elev.update

import androidx.core.content.FileProvider

/** A dedicated subclass avoids device-specific issues with declaring FileProvider directly. */
class UpdateFileProvider : FileProvider()
