import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';

class AppImage extends StatelessWidget {
  const AppImage.network(
    this.url, {
    super.key,
    this.headers = const {},
    this.fit = BoxFit.cover,
    this.placeholderText,
  }) : file = null;
  const AppImage.file(this.file, {super.key, this.fit = BoxFit.contain})
    : url = null,
      headers = const {},
      placeholderText = null;

  final String? url;
  final File? file;
  final Map<String, String> headers;
  final BoxFit fit;
  final String? placeholderText;

  @override
  Widget build(BuildContext context) {
    if (file != null)
      return Image.file(
        file!,
        fit: fit,
        errorBuilder: (_, __, ___) => _placeholder(),
      );
    final resolved = url;
    if (resolved == null || resolved.isEmpty) return _placeholder();
    return CachedNetworkImage(
      imageUrl: resolved,
      httpHeaders: headers,
      fit: fit,
      fadeInDuration: const Duration(milliseconds: 120),
      placeholder: (_, __) => _placeholder(),
      errorWidget: (_, __, ___) =>
          _placeholder(icon: Icons.broken_image_outlined),
    );
  }

  Widget _placeholder({IconData icon = Icons.image_outlined}) => Container(
    color: Colors.white10,
    alignment: Alignment.center,
    child: placeholderText == null
        ? Icon(icon, color: Colors.white38)
        : Text(placeholderText!, style: const TextStyle(color: Colors.white38)),
  );
}
